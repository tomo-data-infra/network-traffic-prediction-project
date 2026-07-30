import json
import time
import ollama
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
from django.db import connection, transaction
from django.db.models import Max, Avg
from .models import EventSession, PingLog, Target
from .serializers import EventSessionSerializer, PingLogSerializer, TargetSerializer
from .utils import features, predictor, anonymizer, llm_router
from datetime import datetime, timedelta, timezone
import psutil

JST = timezone(timedelta(hours=9))

logger = logging.getLogger("netops_agent")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

if psutil is not None:
    rss_mb = psutil.Process().memory_info().rss / (1024 * 1024)
    logger.info("Process memory | rss_mb=%.1f", rss_mb)

class EventSessionViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows event_sessions to be viewed or edited.
    """
    queryset = EventSession.objects.all()
    serializer_class = EventSessionSerializer

class PingLogViewSet(viewsets.ModelViewSet):
    """
    This is for the raw data view. 
    We limit it to the latest 100 rows so it loads INSTANTLY.
    """
    queryset = PingLog.objects.all().order_by('-ts')[:100] 
    serializer_class = PingLogSerializer

class TargetViewSet(viewsets.ModelViewSet):
    queryset = Target.objects.all()
    serializer_class = TargetSerializer

class TrainModelView(APIView):
    """Endpoint to trigger baseline calculation manually from the UI dashboard."""
    def post(self, request):
        try:
            profiles = predictor.train_baseline_profiles(days_back=30)
            return Response({"status": "Model successfully retrained", "profiles": profiles})
        except Exception as e:
            return Response({"error": str(e)}, status=500)

class PingDataView(APIView):
    """
    API endpoint that delivers aggregated network telemetry, statistical forecasts, 
    and concurrent calendar anomalies over a specific request time window.
    """
    def get(self, request):
        # Get the designated period from React
        start_str = request.query_params.get("start")
        end_str = request.query_params.get("end")

        # Fallback logic: Use JST for a 30m window
        now = datetime.now(JST).replace(second=0, microsecond=0)
        
        # DEFAULT: Latest 30 mins if no period is designated
        # DESIGNATED: Specific period if React sends it
        try:
            start = datetime.fromisoformat(start_str).replace(tzinfo=JST) if start_str else now - timedelta(minutes=30)
            end = datetime.fromisoformat(end_str).replace(tzinfo=JST) if end_str else now
        except ValueError:
            return Response(
                {"error": "Invalid date format configuration. Please pass clean ISO 8601 strings."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Defensive security validation windows. Chronological Check. Ensure start occurs before end.
        if start >= end:
            return Response(
                {"error": "Chronological conflict: Start window parameter cannot occur after or equal to the end window."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Out-of-Bounds Memory Ceiling Protection. Limit window requests to a safe window.
        window_duration = end - start
        if window_duration > timedelta(hours=12):
            return Response(
                {"error": "Resource safety constraint: Maximum query limit exceeded. Time windows must not span more than 7 days."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Fetch precisely targeted database slices using Django ORM
        # TODO: Refactor target_id selection dynamically via frontend picker.
        # Pinning query scope strictly to primary target monitoring node (ID: 1) for current release phase.
        logs = PingLog.objects.filter(ts__range=[start, end], target_id=1).order_by('ts')
        
        # Build optimized high-speed array structures safely
        timestamps = np.array([l.ts for l in logs], dtype=object)
        rtts = np.array([l.rtt_ms if l.rtt_ms is not None else np.nan for l in logs], dtype=float)
        timeouts = np.array([1 if l.is_timeout else 0 for l in logs], dtype=int)

        # Process machine learning aggregation arrays over verified time block
        agg_features, agg_times = features.make_features(
            timestamps, rtts, timeouts, agg_seconds=60, tz=JST, start_window=start, end_window=end
        )

        # Generate statistical forecast baseline expectations
        forecast_data = predictor.forecast_remaining_day(start, end)

        # Extract chronological overlaps in business calendar metrics
        overlapping_events = EventSession.objects.filter(start_ts__lt=end, end_ts__gt=start).order_by('start_ts')
        events_payload = [{
            "id": evt.session_id,
            "title": evt.event_name,
            "start": evt.start_ts.isoformat(),
            "end": evt.end_ts.isoformat(),
            "category": evt.session_category,
            "devices": evt.expected_devices
        } for evt in overlapping_events]

        # Deliver clean universal payload package structure
        return Response({
            "times": [t.isoformat() for t in agg_times],
            "features": agg_features[:, 0].tolist() if len(agg_features) > 0 else [],
            "jitters": agg_features[:, 1].tolist() if len(agg_features) > 0 else [],
            "loss_rates": agg_features[:, 2].tolist() if len(agg_features) > 0 else [],
            "forecast": forecast_data,
            "events": events_payload
        })

def run_database_maintenance():
    """
    100% SAFE OPERATION LAYER.
    Updates Materialized Views on an isolated background thread.
    Never deletes or alters raw historical data rows.
    """
    now = timezone.now()
    print(f"[Background DB Task] Maintenance initialized at {now.strftime('%Y-%m-%d %H:%M:%S')} JST")

    try:
        with connection.cursor() as cursor:
            print("[Background DB Task] Refreshing Minute Rollups...")
            cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY minute_rollups;")
            
            print("[Background DB Task] Refreshing Hourly Rollups...")
            cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY hourly_rollups;")
            
            print("[Background DB Task] Refreshing Daily Rollups...")
            cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY daily_rollups;")
            
            print("[Background DB Task] Optimizing database index lookup paths...")
            cursor.execute("ANALYZE ping_logs;")
            
        print("[Background DB Task] Database optimization cycle completed successfully. Zero data loss.")
        
    except Exception as e:
        print(f"[Background DB Task Error] Materialized View refresh failure: {str(e)}")


class DatabaseMaintenanceView(APIView):
    """API endpoint to trigger view updates from the frontend dashboard."""
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
    Advanced Text-to-JSON-to-SQL Semantic NetOps AI Data Agent view.
    Translates natural language queries into secure Cube.js JSON payload definitions.
    Enforces privacy boundary anonymization, cascades multi-tier LLM routing pipelines, 
    and leverages aggregate-aware semantic models for optimized warehouse analytics.
    """
        
    def post(self, request):          
        try:
            # dynamic target tracking baseline configuration
            target_id = 1
            start_time = time.time()

            user_question = request.data.get("question", "").strip()

            if not user_question:
                return Response({"error": "No question provided"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Apply Anonymization Masking immediately to secure network metadata
            safe_masked_question = anonymizer.mask_sensitive_data(user_question)

            # Declarative System Prompt mapping to the Cube Semantic Layer definitions
            system_prompt = f"""
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

            llm_start = time.perf_counter()
            cube_query_raw = llm_router.cascade_llm_router(system_prompt, safe_masked_question)
            llm_elapsed_ms = (time.perf_counter() - llm_start) * 1000

            try:
                logger.info(
                    "LLM payload | elapsed_ms=%.1f | status=%s", llm_elapsed_ms,
                    json.dumps(cube_query_raw, ensure_ascii=False, indent=2)[:1000]
                )
            except TypeError:
                logger.info("LLM payload | elapsed_ms=%.1f | status=%s", llm_elapsed_ms, str(cube_query_raw)[:1000])

            """
            print("--- PAYLOAD RECEIVED FROM LLM ---")
            print(json.dumps(cube_query_raw, indent=2))
            print("---------------------------------")
            # print(f"Structure of cube_query_raw: {cube_query_raw}")
            """

            if isinstance(cube_query_raw, dict) and "error" in cube_query_raw:
                return Response({"answer": "I don't know."}, status=status.HTTP_200_OK)
            
            if isinstance(cube_query_raw, str):
                try:
                    cube_query_raw = json.loads(cube_query_raw.strip())
                except Exception:
                    return Response({"answer": "Malformed AI response structure received."}, status=status.HTTP_200_OK)
            
            # Structural Check: Ensure the LLM returned a schema object we can actually pass down
            if not isinstance(cube_query_raw, dict) or "measures" not in cube_query_raw:
                return Response({
                    "answer": "Could not map query schema details accurately. Please verify your parameter constraints.",
                    "executed_cube_payload": {}
                }, status=status.HTTP_200_OK)
            
            # If anonymizer expects a string input, use json.dumps(cube_query_raw) here
            try:
                final_cube_payload = anonymizer.resolve_tokens_to_db_filters(cube_query_raw)
            except Exception as anon_err:
                return Response({
                    "error": f"Anonymizer resolution mapping failure: {str(anon_err)}"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Generate secure JWT verification signature to unlock Cube Core API access
            cube_secret = settings.CUBE_API_SECRET
            token_payload = {"exp": int(time.time()) + 3600}
            auth_token = jwt.encode(token_payload, cube_secret, algorithm="HS256")

            # Securely dispatch the parameters to the local isolated Cube Core server
            cube_api_endpoint = settings.CUBE_API_URL
            if not cube_api_endpoint.endswith('/cubejs-api/v1/load'):
                cube_api_endpoint = cube_api_endpoint.rstrip('/') + '/cubejs-api/v1/load'

            print(f"Targeting active database core path: {cube_api_endpoint}")

            logger.info("Cube request start | url=%s | payload_keys=%s", cube_api_endpoint, list(final_cube_payload.keys()))

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
                data = body.get("data", [])

                if cube_res.status_code != 200:
                    logger.error("Cube HTTP error | status=%s | body=%s", cube_res.status_code, body)
                elif body.get("error"):
                    logger.warning("Cube application error | %s", body.get("error"))
                elif not data:
                    logger.warning("Cube returned no data")
                else:
                    logger.info("Cube success | rows=%d | slowQuery=%s", len(data), body.get("slowQuery", False))

            except requests.RequestException as e:
                logger.exception("Cube request failed")
            except ValueError as e:
                logger.error("Cube returned invalid JSON | %s", e)

            """
            try:
                cube_res = requests.post(
                    cube_api_endpoint,
                    json={"query": final_cube_payload},
                    headers={"Authorization": auth_token, "Content-Type": "application/json"},
                    timeout=15.0
                )
                logger.info("Cube response | status=%s | body=%s", cube_res.status_code, cube_res.text[:500])
                body = cube_res.json()
                logger.error("Cube returned error body | %s", body)
            except Exception as e:
                logger.error("Network dispatch error to Cube: %s", e)
                cube_res = None
            """
            
            """
            if cube_res is None or cube_res.status_code != 200:
                print("\n[CUBE.JS SEMANTIC ENGINE REJECTION DETAIL]:")
                print(f"Status Code: {cube_res.status_code}")
                print(f"Error Message Context: {cube_res.text}\n")
                return Response({"error": f"Semantic layer execution failure: {cube_res.text}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            """
            
            if cube_res is None or cube_res.status_code != 200:
                err_msg = cube_res.text if cube_res else "Connection Timeout / Unreachable"
                print(f"[CUBE.JS SEMANTIC ENGINE REJECTION DETAIL]: {err_msg}")
                
                # FALLBACK GATE: If Cube fails, clear execution and explicitly drop to Tier 3 loop
                # instead of throwing a generic 500 error page to the frontend UI
                cube_query_raw = llm_router.query_tier3_local_ollama(system_prompt, safe_masked_question)
                return Response({"answer": cube_query_raw}, status=status.HTTP_200_OK)
            

            """
            # Your Safe Gateway Catch Logic Block
            if cube_res is None or cube_res.status_code != 200:
                err_msg = cube_res.text if cube_res else "Connection Timeout / Unreachable"
                print(f"[CUBE.JS SEMANTIC ENGINE REJECTION DETAIL]: {err_msg}")
                
                # If Cube is unreachable, capture the raw response payload text generated by Tier 2
                raw_payload_dict = cube_query_raw 
                
                # FIX: Run it through the anonymizer dictionary lookup to restore your database IPs instantly
                try:
                    final_unmasked_fallback = anonymizer.resolve_tokens_to_db_filters(raw_payload_dict)
                except Exception:
                    final_unmasked_fallback = raw_payload_dict
                
                return Response({"answer": final_unmasked_fallback}, status=status.HTTP_200_OK)
            """
            analytics_data = cube_res.json().get("data", [])

            # Synthesize data results back into natural language for user display
            synthesis_prompt = f"Synthesize this database data context into a concise message answer responding to: '{user_question}'. Data: {json.dumps(analytics_data)}"
            
            """          
            # Using Tier 3 local Qwen framework for safe synthesis fallback
            from ollama import generate as ollama_generate
            final_text_res = ollama_generate(
                model='qwen2.5:1.5b',
                prompt=synthesis_prompt
            )
            """

            # Use the existing settings URL to talk directly to Ollama's native endpoint
            ollama_endpoint = settings.OLLAMA_API_URL
            if not ollama_endpoint.endswith('/api/generate'):
                ollama_endpoint = ollama_endpoint.rstrip('/') + '/api/generate'
                        
            payload = {
                "model": "qwen2.5:1.5b",
                "prompt": synthesis_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    # "num_predict": 150
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
                # Safe fallback so your API never returns a 500 error if Ollama is slow
                final_text = f"Data retrieved successfully. (Local synthesis layer offline: {str(ollama_err)})"
            
            execution_time = time.time() - start_time
            logger.info("Request completed | total_elapsed_s=%.3f | rss_mb=%.1f", execution_time, rss_mb)
    
            # Log metrics to your `ai_agent_logs` table here before return...
            return Response({
                "answer": final_text,
                "executed_cube_payload": final_cube_payload,
                "execution_seconds": round(execution_time, 3)
            }, status=status.HTTP_200_OK)

        except Exception as e:
            import traceback
            print("\n[CRITICAL BACKEND CRASH LOG] Detailed Traceback Info:")
            traceback.print_exc()
            print("-----------------------------------------------------\n")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
