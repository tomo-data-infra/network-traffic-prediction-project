import json
import time
import ollama
import numpy as np
import threading
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import connection, transaction
from django.db.models import Max, Avg
from .models import EventSession, PingLog, Target
from .serializers import EventSessionSerializer, PingLogSerializer, TargetSerializer
from .utils import features, predictor
from django.utils import timezone as django_tz
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

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

class TrafficAgentView(APIView):
    """
    Advanced Text-to-SQL NetOps Ingestion Agent view.
    Translates loose natural language text into targeted database queries.
    Enforces strict read-only parameters and audits AI performance metrics.
    """

    def query_database(self, sql_string):
        """Executes read-only SQL queries securely with structural safety blocks."""
        try:
            clean_sql = sql_string.strip().rstrip(';')
            upper_sql = clean_sql.upper()

            # 🛑 CRITICAL SECURITY GUARDRAIL: Block any attempt to delete, alter, or drop data structures
            destructive_keywords = [
                "DELETE", "DROP", "TRUNCATE", "UPDATE", "INSERT", 
                "ALTER", "GRANT", "REVOKE", "CREATE", "REPLACE", 
                "VACUUM", "COMMENT", "EXECUTE", "PREPARE"
            ]
            if any(keyword in upper_sql for keyword in destructive_keywords):
                print(f"[SECURITY ALERT] Destructive query attempt blocked: {clean_sql}")
                return "Database Error: Operation access denied. Only SELECT queries are permitted."

            # 💡 SAFE AUTO-SORT UPGRADE: If it's a maximum query but lacks a limit, append it safely
            if "HIGHEST_RTT" in upper_sql and "ORDER BY" not in upper_sql:
                clean_sql += " ORDER BY highest_rtt DESC LIMIT 1"
            elif "MEAN_RTT" in upper_sql and "ORDER BY" not in upper_sql:
                clean_sql += " ORDER BY mean_rtt DESC LIMIT 1"
            elif "PACKET_LOSS_RATE" in upper_sql and "ORDER BY" not in upper_sql:
                clean_sql += " ORDER BY packet_loss_rate DESC LIMIT 1"
            elif "LIMIT" not in upper_sql:
                clean_sql += " LIMIT 1"
            
            with connection.cursor() as cursor:
                cursor.execute(clean_sql)
                if not cursor.description:
                    return json.dumps([])
                columns = [col.name for col in cursor.description]
                rows = cursor.fetchmany(5) # Restrict evaluation blocks to safe performance ceilings
                return json.dumps([dict(zip(columns, row)) for row in rows], default=str)
        except Exception as e:
            return f"Database Error: {str(e)}"
        
    def post(self, request):
        user_question = request.data.get("question", "").strip()

        # NOTE / FUTURE TASK:
        # Dynamic target assignment (target_id selection via frontend picker or LookML orchestration)
        # is scheduled for Phase 2 deployment. Tracking defaults strictly to Core Node ID: 1.
        target_id = 1

        if not user_question:
            return Response({"error": "No question provided"}, status=status.HTTP_400_BAD_REQUEST)

        # SYSTEM PROMPT: Strict Read-Only Rules + Full Tiered View Awareness
        system_prompt = """
        You are an AI NetOps Data Agent. Your task is to analyze the user's network query and return a valid JSON object containing an optimized PostgreSQL query string.

        DATABASE LAYERS AVAILABLE:
        1. View: daily_rollups (1-day aggregates. Use ONLY for broad macro queries spanning more than 7 days, full weeks, or months).
           - EXACT columns you can use: ts_day, target_id, mean_rtt, highest_rtt, lowest_rtt, packet_loss_rate
        2. View: hourly_rollups (1-hour aggregates. Use ONLY for queries spanning between 24 hours and 7 days, or when asking for a specific hour block like '12:00 to 13:00').
           - EXACT columns you can use: ts_hour, target_id, mean_rtt, highest_rtt, lowest_rtt, packet_loss_rate
        3. View: minute_rollups (1-minute aggregates. Use for detailed intraday queries spanning 2 to 24 hours).
           - EXACT columns you can use: ts_minute, target_id, mean_rtt, highest_rtt, lowest_rtt, packet_loss_rate

        TEMPORAL ROUTING RULES:
        - If the question asks about a specific day or date (e.g., 'June 19'), you MUST query FROM 'minute_rollups'.
        - To return a single peak or highest metric value with its time, you MUST select BOTH the target metric and the 'ts_minute' column, and you MUST always append 'ORDER BY [metric_column] DESC LIMIT 1' to ensure only ONE row returns.
        - You MUST always enforce the filter 'target_id = {target_id}' in your WHERE clause statements. Do NOT use any other target ID number.

        CRITICAL COLUMN DEFINITIONS:
        - 'mean_rtt' stores the 1-minute AVERAGE baseline latency value. Use this when the user asks for "highest mean RTT", "highest average", or "worst average baseline".
        - 'highest_rtt' stores the absolute worst 1-second INSTANTaneous latency spike that happened within that minute. Use this when the user asks for "highest RTT", "instant peak", "momentary surge", or "worst single second".

        FEW-SHOT TRANSLATION SAMPLES (INJECTED TARGET_ID={target_id}):
        
        User: "What was the highest RTT on June 19?"
        Target: Fetch HIGHEST instantaneous spike value and its time.
        Query: {"sql": "SELECT ts_minute, highest_rtt FROM minute_rollups WHERE target_id = 1 AND ts_minute >= '2026-06-19 00:00:00+09' AND ts_minute < '2026-06-20 00:00:00+09' ORDER BY highest_rtt DESC LIMIT 1;"}

        User: "What was the highest mean RTT on June 19?"
        Target: Fetch HIGHEST 1-minute baseline average and its time.
        Query: {"sql": "SELECT ts_minute, mean_rtt FROM minute_rollups WHERE target_id = 1 AND ts_minute >= '2026-06-19 00:00:00+09' AND ts_minute < '2026-06-20 00:00:00+09' ORDER BY mean_rtt DESC LIMIT 1;"}

        User: "What was the highest packet loss rate on June 19?"
        Target: Fetch HIGHEST packet drop percentage and its time.
        Query: {"sql": "SELECT ts_minute, packet_loss_rate FROM minute_rollups WHERE target_id = 1 AND ts_minute >= '2026-06-19 00:00:00+09' AND ts_minute < '2026-06-20 00:00:00+09' ORDER BY packet_loss_rate DESC LIMIT 1;"}

        CRITICAL SECURITY & PERFORMANCE RULES:
        - You are strictly a READ-ONLY data engine assistant. You are ONLY allowed to generate 'SELECT' queries.
        - You are forbidden from modifying any data, schemas, or database states.
        - NEVER generate commands containing: "DELETE", "DROP", "TRUNCATE", "UPDATE", "INSERT", "ALTER", "GRANT", "REVOKE", "CREATE", "REPLACE", "VACUUM", or "COMMENT".
        - ALWAYS filter by "target_id = 1".
        - NEVER use date formatting functions on timestamp columns like "ts_minute::date" or "EXTRACT()". Use explicit chronological operators (>=, <) to keep queries optimized.
        - MANDATORY ROUTING RULE: For any question about a specific date or single day (e.g., 'May 22'), you MUST query FROM 'minute_rollups' using the 'ts_minute' column.
        - EXPLICIT SYNTAX EXAMPLE FOR A SINGLE DATE: SELECT highest_rtt FROM minute_rollups WHERE ts_minute >= '2026-05-22 00:00:00+09' AND ts_minute < '2026-05-23 00:00:00+09';
        - Assume the current year is 2026 if omitted.

        OUTPUT FORMAT:
        Output ONLY a valid JSON object matching the schema below. Never forget the 'ORDER BY' and 'LIMIT 1' statements for maximum metrics questions.
        {"sql": "SELECT ..."}

        If the question cannot be answered, is dangerous, or is unrelated, return exactly:
        {"error": "I don't know."}
        """

        # Start tracking total response processing time for performance audits
        start_time = time.time()
        sql_query = "N/A"
        db_result = "N/A"

        try:
            # Fetch raw query generation directives from local LLM node
            intent_res = ollama.generate(
                model='qwen2.5:1.5b',
                system=system_prompt, 
                prompt=user_question,
                options={"temperature": 0.0}
                )
            
            # Sanitize accidental markdown wrappers out of structural JSON responses
            raw_response = intent_res['response'].strip()
            if raw_response.startswith("```json"):
                raw_response = raw_response.lstrip("```json").rstrip("```")
            elif raw_response.startswith("```"):
                raw_response = raw_response.lstrip("```").rstrip("```")
                
            intent_data = json.loads(raw_response.strip())

            if "error" in intent_data:
                return Response({"answer": "I don't know. / 分かりません。"})

            # Extract and sanitize the generated SQL string directly
            sql_query = intent_data.get("sql")
            if not sql_query:
                return Response({"answer": "I don't know. / 分かりません。"})
            
            print(f"[Generated AI SQL Query]: {sql_query}")

            # Query the indexed PostgreSQL tables instantly via protected cursor method
            db_result = self.query_database(sql_query)
            
            # Feed results back to model to write a natural operational overview message
            print("[AI Agent] Requesting natural linguistic dashboard summary...")
            synthesis_prompt = f"User Question: {user_question}\nDatabase Output Matrix: {db_result}"
            
            final_res = ollama.chat(
                model='qwen2.5:1.5b',
                messages=[
                    {
                        'role': 'system', 
                        'content': (
                            'Synthesize a short, direct network operational summary response. '
                            'CRITICAL: Always display RTT latency numbers in exact milliseconds (ms) '
                            'as written in the database matrix. Do not round up or convert them to seconds. '
                            'If the user question is in Japanese, respond in Japanese. If in English, respond in English.'
                        )
                    },
                    {'role': 'user', 'content': synthesis_prompt}
                ]
            )
            
            final_text = final_res['message']['content'].strip()

            # Collects timestamps, prompts, SQL execution paths, and metrics to continuous model profiling tables
            execution_latency = time.time() - start_time
            try:
                with connection.cursor() as audit_cursor:
                    audit_cursor.execute("""
                        INSERT INTO ai_agent_logs (ts, user_prompt, generated_sql, db_output, final_response, latency_seconds)
                        VALUES (NOW(), %s, %s, %s, %s, %s);
                    """, (user_question, sql_query, db_result, final_text, execution_latency))
            except Exception as log_err:
                print(f"[AUDIT LOG WARNING] Could not save agent metrics to table: {str(log_err)}")
            
            return Response({"answer": final_text})

        except Exception as e:
            print(f"Agent Pipeline Failure Trace: {str(e)}")
            return Response({"answer": "I don't know. / 分かりません。"})
