import json
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
# Import your features script (assuming it's in a utils subfolder)
from .utils import features, predictor
from django.utils import timezone as django_tz # For Django-specific time needs
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

# Keep your existing ViewSet for Calendar CRUD
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

# Add the new APIView for the ML Traffic Monitor
class PingDataView(APIView):
    def get(self, request):
        # 1. Get the designated period from React
        start_str = request.query_params.get("start")
        end_str = request.query_params.get("end")

        # Fallback logic: Use JST for a 30m window
        now = datetime.now(JST).replace(second=0, microsecond=0)
        
        # 2. DEFAULT: Latest 30 mins if no period is designated
        # DESIGNATED: Specific period if React sends it
        start = datetime.fromisoformat(start_str).replace(tzinfo=JST) if start_str else now - timedelta(minutes=30)
        end = datetime.fromisoformat(end_str).replace(tzinfo=JST) if end_str else now
        
        # 3. Fetch ONLY the requested slice  Fetch Network Telemetry. Gather Historical Actual Logs
        logs = PingLog.objects.filter(ts__range=[start, end], target_id=1).order_by('ts')
        
        # --- CRITICAL MISSING BLOCK START ---
        # Force explicit types to ensure empty dataframes do not cause out-of-bounds array crashes
        timestamps = np.array([l.ts for l in logs], dtype=object)
        rtts = np.array([l.rtt_ms if l.rtt_ms is not None else np.nan for l in logs], dtype=float)
        timeouts = np.array([1 if l.is_timeout else 0 for l in logs], dtype=int)
        # --- CRITICAL MISSING BLOCK END ---

        # 4. ML Processing for that specific window
        agg_features, agg_times = features.make_features(
            timestamps, rtts, timeouts, agg_seconds=60, tz=JST, start_window=start, end_window=end
        )

        # 2. Compute Statistical Forecast Curve Over Same Window
        forecast_data = predictor.forecast_remaining_day(start, end)

        # 3. Gather Calendar Overlaps
        # 4. Return the JSON package
        # FETCH OVERLAPPING CALENDAR EVENTS FOR THIS VISUAL WINDOW
        # If an event starts before the window ends, and ends after the window starts, it overlaps.
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
            "features": agg_features[:, 0].tolist() if len(agg_features) > 0 else [], # Mean RTT
            "jitters": agg_features[:, 1].tolist() if len(agg_features) > 0 else [],  # Jitter Standard Deviation
            "loss_rates": agg_features[:, 2].tolist() if len(agg_features) > 0 else [],
            "forecast": forecast_data,  # Direct alignment vector mapping
            "events": events_payload # Forwarded payload for the concurrent timeline track
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

# This uses Ollama to translate natural language into structured parameters or direct queries, handles both English and Japanese safely and queries the database using high-performance Django ORM filters.
class TrafficAgentView(APIView):

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

            # Force protective row limits if the query is an open-ended dump
            if "LIMIT" not in upper_sql and "COUNT" not in upper_sql and "AVG" not in upper_sql and "MAX" not in upper_sql:
                clean_sql += " LIMIT 100"
            
            with connection.cursor() as cursor:
                cursor.execute(clean_sql)
                # columns = [col for col in cursor.description]
                columns = [col.name for col in cursor.description]
                rows = cursor.fetchmany(100) 
                return json.dumps([dict(zip(columns, row)) for row in rows], default=str)
        except Exception as e:
            return f"Database Error: {str(e)}"
        
    def post(self, request):
        user_question = request.data.get("question", "").strip()
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
        4. Table: ping_logs (Raw 1-second entries. Use ONLY when the user explicitly asks for precise, second-by-second data or single-second specific details).
           - EXACT columns you can use: ts, rtt_ms, is_timeout, target_id

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
        Output ONLY a valid JSON object matching this schema. Do not wrap it in markdown tags.
        {"sql": "SELECT ..."}

        If the question cannot be answered, is dangerous, or is unrelated, return exactly:
        {"error": "I don't know."}
        """

        try:
            # 1. Get raw query instructions from Ollama
            intent_res = ollama.generate(
                model='qwen2.5:1.5b', #'llama3', # 'qwen2.5:1.5b', 
                system=system_prompt, 
                prompt=user_question,
                options={"temperature": 0.0}
                )
            
            # Clean possible markdown wrapping code blocks if generated by accident
            raw_response = intent_res['response'].strip()
            if raw_response.startswith("```json"):
                raw_response = raw_response.lstrip("```json").rstrip("```")
            elif raw_response.startswith("```"):
                raw_response = raw_response.lstrip("```").rstrip("```")
                
            intent_data = json.loads(raw_response.strip())

            if "error" in intent_data:
                return Response({"answer": "I don't know. / 分かりません。"})

            # 2. Extract the generated SQL string directly
            sql_query = intent_data.get("sql")
            if not sql_query:
                return Response({"answer": "I don't know. / 分かりません。"})
            
            print(f"[Generated AI SQL Query]: {sql_query}")

            # 3. Query your indexed PostgreSQL tables instantly via protected cursor method
            db_result = self.query_database(sql_query)
            
            # 4. Feed the raw table results back to Ollama to write a natural message response
            synthesis_prompt = f"""
            User Question: {user_question}
            Database Execution Output Matrix: {db_result}
            
            Synthesize a short, direct network operational summary response. 
            If the user question is in Japanese, respond in Japanese. If in English, respond in English.
            """
            final_res = ollama.generate(
                model='qwen2.5:1.5b', #'llama3', 
                prompt=synthesis_prompt
                )
            
            return Response({"answer": final_res['response'].strip()})

        except Exception as e:
            print(f"Agent Pipeline Failure Trace: {str(e)}")
            return Response({"answer": "I don't know. / 分かりません。"})
