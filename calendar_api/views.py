import json
import time
import jwt
import numpy as np
import threading
import requests
import logging
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.utils import timezone as django_tz
from django.db import connection
from .models import EventSession, PingLog, Target, AIAgentLog
from .serializers import EventSessionSerializer, PingLogSerializer, TargetSerializer
from .utils import features, predictor, anonymizer, llm_router
from .permissions import IsAdminOrReadOnly
from datetime import datetime, timedelta, timezone
import psutil

JST = timezone(timedelta(hours=9))

logger = logging.getLogger("netops_agent")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

class EventSessionViewSet(viewsets.ModelViewSet):
    """API endpoint that allows event_sessions to be viewed or edited."""
    queryset = EventSession.objects.all()
    serializer_class = EventSessionSerializer
    permission_classes = [IsAdminOrReadOnly]


class AdminLoginView(APIView):
    """Issues a short-lived JWT after checking the admin password server-side."""
    def post(self, request):
        password = request.data.get("password", "")
        if not settings.ADMIN_PASSWORD or password != settings.ADMIN_PASSWORD:
            return Response({"error": "Incorrect password"}, status=status.HTTP_401_UNAUTHORIZED)

        token = jwt.encode(
            {"role": "admin", "exp": int(time.time()) + 8 * 3600},
            settings.SECRET_KEY,
            algorithm="HS256",
        )
        return Response({"token": token})

class PingLogViewSet(viewsets.ModelViewSet):
    """Raw ping_logs view, limited to the latest 100 rows."""
    queryset = PingLog.objects.all()
    serializer_class = PingLogSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        return PingLog.objects.all().order_by('-ts')[:100]

class TargetViewSet(viewsets.ModelViewSet):
    queryset = Target.objects.all()
    serializer_class = TargetSerializer
    permission_classes = [IsAdminOrReadOnly]

class TrainModelView(APIView):
    """Endpoint to trigger baseline calculation manually from the UI dashboard."""
    permission_classes = [IsAdminOrReadOnly]

    def post(self, request):
        try:
            profiles = predictor.train_baseline_profiles(days_back=30)
            return Response({"status": "Model successfully retrained", "profiles": profiles})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PingDataView(APIView):
    """
    Returns aggregated telemetry, a statistical forecast, and overlapping calendar events for a time window.
    Intentionally unauthenticated (read-only, GET-only) so the public dashboard demo works without a login.
    """
    def get(self, request):
        start_str = request.query_params.get("start")
        end_str = request.query_params.get("end")

        # Default to the latest 30 minutes (JST) if no window is given
        now = datetime.now(JST).replace(second=0, microsecond=0)
        try:
            start = datetime.fromisoformat(start_str).replace(tzinfo=JST) if start_str else now - timedelta(minutes=30)
            end = datetime.fromisoformat(end_str).replace(tzinfo=JST) if end_str else now
        except ValueError:
            return Response(
                {"error": "Invalid date format configuration. Please pass clean ISO 8601 strings."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if start >= end:
            return Response(
                {"error": "Chronological conflict: Start window parameter cannot occur after or equal to the end window."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Cap window size so aggregation stays within a safe memory footprint
        window_duration = end - start
        if window_duration > timedelta(hours=12):
            return Response(
                {"error": "Resource safety constraint: Maximum query limit exceeded. Time windows must not span more than 12 hours."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # TODO: target_id is hardcoded to the single monitored node; make this
        # selectable once the frontend supports picking a target.
        logs = PingLog.objects.filter(ts__range=[start, end], target_id=1).order_by('ts')

        timestamps = np.array([l.ts for l in logs], dtype=object)
        rtts = np.array([l.rtt_ms if l.rtt_ms is not None else np.nan for l in logs], dtype=float)
        timeouts = np.array([1 if l.is_timeout else 0 for l in logs], dtype=int)

        agg_features, agg_times = features.make_features(
            timestamps, rtts, timeouts, agg_seconds=60, tz=JST, start_window=start, end_window=end
        )

        forecast_data = predictor.forecast_remaining_day(start, end)

        overlapping_events = EventSession.objects.filter(start_ts__lt=end, end_ts__gt=start).order_by('start_ts')
        events_payload = [{
            "id": evt.session_id,
            "title": evt.event_name,
            "start": evt.start_ts.isoformat(),
            "end": evt.end_ts.isoformat(),
            "category": evt.session_category,
            "devices": evt.expected_devices
        } for evt in overlapping_events]

        return Response({
            "times": [t.isoformat() for t in agg_times],
            "features": agg_features[:, 0].tolist() if len(agg_features) > 0 else [],
            "jitters": agg_features[:, 1].tolist() if len(agg_features) > 0 else [],
            "loss_rates": agg_features[:, 2].tolist() if len(agg_features) > 0 else [],
            "forecast": forecast_data,
            "events": events_payload
        })

def run_database_maintenance():
    """Refreshes materialized views on a background thread. Read-only against raw ping_logs."""
    now = django_tz.now()
    logger.info(
        "[Background DB Task] Maintenance initialized at %s JST",
        now.astimezone(JST).strftime("%Y-%m-%d %H:%M:%S")
    )

    try:
        with connection.cursor() as cursor:
            logger.info("[Background DB Task] Refreshing minute_rollups...")
            cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY minute_rollups;")

            logger.info("[Background DB Task] Refreshing hourly_rollups...")
            cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY hourly_rollups;")

            logger.info("[Background DB Task] Refreshing daily_rollups...")
            cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY daily_rollups;")

            logger.info("[Background DB Task] Analyzing ping_logs for planner statistics...")
            cursor.execute("ANALYZE ping_logs;")

        logger.info("[Background DB Task] Database optimization cycle completed successfully.")
    except Exception:
        logger.exception("[Background DB Task] Materialized view refresh failure")

class DatabaseMaintenanceView(APIView):
    """API endpoint to trigger view updates from the frontend dashboard."""
    permission_classes = [IsAdminOrReadOnly]

    def post(self, request, *args, **kwargs):
        try:
            maintenance_thread = threading.Thread(target=run_database_maintenance)
            maintenance_thread.daemon = True
            maintenance_thread.start()
            
            return Response({
                "status": "success",
                "message": "Database optimization sequence started in the background."
            }, status=status.HTTP_202_ACCEPTED)
        except Exception as e:
            return Response({
                "status": "error",
                "message": f"Failed to initialize background task: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class NetOpsAgentCoreView(APIView):
    """
    Text-to-JSON-to-SQL NetOps agent: translates a natural-language question into
    a Cube.js query, executes it, and synthesizes a natural-language answer.

    Intentionally unauthenticated: this is a public chat demo, and every query is
    structurally read-only (see llm_router/anonymizer) and fully audited via AIAgentLog.
    """

    def post(self, request):
        try:
            start_time = time.time()

            user_question = request.data.get("question", "").strip()
            if not user_question:
                return Response({"error": "No question provided"}, status=status.HTTP_400_BAD_REQUEST)

            safe_masked_question, ip_token_map = self._mask_question(user_question)
            system_prompt = self._build_system_prompt()

            cube_query_raw, llm_elapsed_ms = self._run_llm_cascade(system_prompt, safe_masked_question)
            self._log_llm_payload(cube_query_raw, llm_elapsed_ms)

            cube_query, early_response = self._parse_and_validate_llm_query(cube_query_raw)
            if early_response is not None:
                return early_response

            try:
                final_cube_payload = anonymizer.resolve_tokens_to_db_filters(cube_query, ip_token_map)
            except Exception as anon_err:
                return Response({
                    "error": f"Anonymizer resolution mapping failure: {str(anon_err)}"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            cube_res, body, analytics_data = self._dispatch_cube_query(final_cube_payload)

            if cube_res is None or getattr(cube_res, "status_code", None) != 200:
                err_msg = cube_res.text if cube_res else "Connection Timeout / Unreachable"
                logger.warning("Cube fallback triggered | %s", err_msg)
                fallback_answer_text = llm_router.query_tier3_local_ollama(system_prompt, safe_masked_question)
                return Response({"answer": fallback_answer_text}, status=status.HTTP_200_OK)

            self._log_cube_result(body, analytics_data)

            final_text = self._synthesize_answer(user_question, analytics_data)

            execution_time = time.time() - start_time
            self._log_completion(execution_time)
            self._log_interaction(user_question, final_cube_payload, analytics_data, final_text, execution_time)

            return Response({
                "answer": final_text,
                "executed_cube_payload": final_cube_payload,
                "execution_seconds": round(execution_time, 3)
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("Critical backend crash")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ---- Stage 1: input sanitization -------------------------------------------------

    def _mask_question(self, user_question):
        """Mask IPs before anything leaves the process (LLM calls, logs)."""
        return anonymizer.mask_sensitive_data(user_question)

    def _build_system_prompt(self):
        return f"""
            You are an AI NetOps Data Agent. Your task is to translate network queries into a Cube.js semantic layer query JSON object.

            AVAILABLE MODEL TARGETS:
            Measures:
            - "PingLogs.highestRtt": Absolute worst 1-second instantaneous latency spike.
            - "PingLogs.meanRtt": 1-minute baseline average latency.
            - "PingLogs.packetLossRate": Percentage of packet drops.

            Dimensions:
            - "PingLogs.ts": The timestamp of network log events.
            - "Targets.ip": The target IP address string variable.

            FILTER COMPLIANCE REQ:
            - You MUST always apply a filter parameter constraining "Targets.ip" to equal the specified node string (e.g. "TARGET_NODE_1").

            OUTPUT METRIC TEMPLATE EXAMPLE:
            {{
            "measures": ["PingLogs.highestRtt"],
            "timeDimensions": [{{
                "dimension": "PingLogs.ts",
                "dateRange": ["2026-06-19", "2026-06-19"],
                "granularity": "minute"
            }}],
            "filters": [{{
                "member": "Targets.ip",
                "operator": "equals",
                "values": ["TARGET_NODE_1"]
            }}],
            "order": {{"PingLogs.highestRtt": "desc"}},
            "limit": 1
            }}
            Assume current year is 2026 if omitted. Return raw JSON block object only.
            """

    # ---- Stage 2: LLM cascade ---------------------------------------------------------

    def _run_llm_cascade(self, system_prompt, masked_question):
        llm_start = time.perf_counter()
        cube_query_raw = llm_router.cascade_llm_router(system_prompt, masked_question)
        llm_elapsed_ms = (time.perf_counter() - llm_start) * 1000
        return cube_query_raw, llm_elapsed_ms

    def _log_llm_payload(self, cube_query_raw, llm_elapsed_ms):
        try:
            logger.info(
                "LLM payload | elapsed_ms=%.1f | status=%s", llm_elapsed_ms,
                json.dumps(cube_query_raw, ensure_ascii=False, indent=2)[:1000]
            )
        except TypeError:
            logger.info("LLM payload | elapsed_ms=%.1f | status=%s", llm_elapsed_ms, str(cube_query_raw)[:1000])

    def _parse_and_validate_llm_query(self, cube_query_raw):
        """Returns (parsed_query, None) on success, or (None, early_response) to short-circuit the request."""
        if isinstance(cube_query_raw, dict) and "error" in cube_query_raw:
            return None, Response({"answer": "I don't know."}, status=status.HTTP_200_OK)

        if isinstance(cube_query_raw, str):
            try:
                cube_query_raw = json.loads(cube_query_raw.strip())
            except Exception:
                return None, Response({"answer": "Malformed AI response structure received."}, status=status.HTTP_200_OK)

        if not isinstance(cube_query_raw, dict) or "measures" not in cube_query_raw:
            return None, Response({
                "answer": "Could not map query schema details accurately. Please verify your parameter constraints.",
                "executed_cube_payload": {}
            }, status=status.HTTP_200_OK)

        return cube_query_raw, None

    # ---- Stage 3: Cube.js dispatch -----------------------------------------------------

    def _dispatch_cube_query(self, final_cube_payload):
        cube_secret = settings.CUBE_API_SECRET
        token_payload = {"exp": int(time.time()) + 3600}
        auth_token = jwt.encode(token_payload, cube_secret, algorithm="HS256")

        cube_api_endpoint = llm_router.ensure_endpoint_suffix(settings.CUBE_API_URL, '/cubejs-api/v1/load')

        logger.info("Cube request start | url=%s | payload_keys=%s", cube_api_endpoint, list(final_cube_payload.keys()))

        cube_res = None
        body = {}
        analytics_data = []

        cube_start = time.perf_counter()
        try:
            cube_res = requests.post(
                cube_api_endpoint,
                json={"query": final_cube_payload},
                headers={"Authorization": auth_token, "Content-Type": "application/json"},
                timeout=15.0
            )
            cube_elapsed_ms = (time.perf_counter() - cube_start) * 1000
            logger.info("Cube request done | elapsed_ms=%.1f | status=%s", cube_elapsed_ms, cube_res.status_code)

            body = cube_res.json()
            analytics_data = body.get("data", [])
        except requests.RequestException:
            logger.exception("Cube request failed")
        except ValueError as e:
            logger.error("Cube returned invalid JSON | %s", e)

        return cube_res, body, analytics_data

    def _log_cube_result(self, body, analytics_data):
        if body.get("error"):
            logger.warning("Cube application error | %s", body.get("error"))
        elif not analytics_data:
            logger.warning("Cube returned no data | body=%s", body)
        else:
            logger.info("Cube success | rows=%d | slowQuery=%s", len(analytics_data), body.get("slowQuery", False))

    # ---- Stage 4: answer synthesis ------------------------------------------------------

    def _synthesize_answer(self, user_question, analytics_data):
        synthesis_prompt = f"Synthesize this database data context into a concise message answer responding to: '{user_question}'. Data: {json.dumps(analytics_data)}"

        ollama_endpoint = llm_router.ensure_endpoint_suffix(settings.OLLAMA_API_URL, '/api/generate')

        payload = {
            "model": "qwen2.5:1.5b",
            "prompt": synthesis_prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
            }
        }

        ollama_start = time.perf_counter()
        try:
            synthesis_res = requests.post(ollama_endpoint, json=payload, timeout=60.0)
            ollama_elapsed_ms = (time.perf_counter() - ollama_start) * 1000
            if synthesis_res.status_code == 200:
                final_text = synthesis_res.json().get('response', '').strip()
            else:
                final_text = f"Data retrieved successfully, but local synthesis node returned status {synthesis_res.status_code}."
            logger.info("Ollama synthesis done | elapsed_ms=%.1f | status=%s", ollama_elapsed_ms, synthesis_res.status_code)
        except Exception as ollama_err:
            # Ollama being slow/offline shouldn't turn into a 500 for the user
            final_text = f"Data retrieved successfully. (Local synthesis layer offline: {str(ollama_err)})"

        return final_text

    # ---- Stage 5: diagnostics & audit trail ---------------------------------------------

    def _log_completion(self, execution_time):
        rss_mb = psutil.Process().memory_info().rss / (1024 * 1024)
        logger.info("Request completed | total_elapsed_s=%.3f | rss_mb=%.1f", execution_time, rss_mb)

    def _log_interaction(self, user_question, final_cube_payload, analytics_data, final_text, execution_time):
        try:
            AIAgentLog.objects.create(
                user_prompt=user_question,
                generated_sql=json.dumps(final_cube_payload, ensure_ascii=False),
                db_output=json.dumps(analytics_data, ensure_ascii=False)[:10000],
                final_response=final_text,
                latency_seconds=execution_time,
            )
        except Exception:
            logger.exception("Failed to write ai_agent_logs entry")
