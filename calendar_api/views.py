import json
import ollama
import numpy as np
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
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

# This uses Ollama to translate natural language into structured parameters or direct queries, handles both English and Japanese safely and queries the database using high-performance Django ORM filters.
class TrafficAgentView(APIView):
    def post(self, request):
        user_question = request.data.get("question", "").strip()
        if not user_question:
            return Response({"error": "No question provided"}, status=status.HTTP_400_BAD_REQUEST)

        # SYSTEM PROMPT: Forces Ollama to act as a structured intent parser
        system_prompt = """
        You are an AI NetOps Data Agent. Your task is to analyze the user's network query and return a valid JSON object containing an optimized PostgreSQL query string.

        DATABASE LAYERS AVAILABLE:
        1. View: ping_logs_1m (A 1-minute rollup summary table. Use this for ALL wide macro queries spanning multiple days or an entire month to ensure lightning-fast speed).
           Columns:
             - ts_minute: TIMESTAMP WITH TIME ZONE
             - target_id: INTEGER
             - mean_rtt: DOUBLE PRECISION
             - highest_rtt: DOUBLE PRECISION
             - lowest_rtt: DOUBLE PRECISION
             - jitter: DOUBLE PRECISION
             - packet_loss_rate: DOUBLE PRECISION

        2. Table: ping_logs (Raw per-second network logs. Use ONLY for precise calculations within a single day/hour or exact timestamps).
           Columns:
             - ts: TIMESTAMP WITH TIME ZONE
             - rtt_ms: DOUBLE PRECISION
             - is_timeout: BOOLEAN
             - target_id: INTEGER

        CRITICAL PERFORMANCE RULES:
        - ALWAYS filter by "target_id = 1".
        - NEVER use date formatting functions on the timestamp columns like "ts::date" or "EXTRACT()". Use explicit chronological operators (>=, <, NOW() - INTERVAL) to keep queries optimized.
        - Assume the current year is 2026 if omitted.

        OUTPUT FORMAT:
        Output ONLY a valid JSON object matching this schema. Do not wrap it in markdown tags like ```json.
        {"sql": "SELECT ..."}

        If the question cannot be answered or is unrelated, return exactly:
        {"error": "I don't know."}
        """

        try:
            # 1. Ask Ollama to evaluate intent layout
            intent_res = ollama.generate(model='llama3', system=system_prompt, prompt=user_question)
            intent_data = json.loads(intent_res['response'].strip())

            if "error" in intent_data:
                return Response({"answer": "I don't know. / 分かりません。"})

            intent = intent_data.get("intent")
            target_date_str = intent_data.get("date")
            parsed_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

            # 2. Map Intents cleanly to Django ORM Queries instead of raw raw SQL concatenation strings
            db_result = "No data found."
            
            if intent == "highest_rtt":
                max_val = PingLog.objects.filter(ts__date=parsed_date, target_id=1).aggregate(Max('rtt_ms'))['rtt_ms__max']
                if max_val: db_result = f"Highest RTT: {max_val:.2f} ms"

            elif intent == "average_rtt" or intent == "specific_rtt":
                hour = intent_data.get("hour", 0)
                minute = intent_data.get("minute", None)
                
                if minute is not None:
                    # Precise 1-minute window block matching
                    start_time = datetime.combine(parsed_date, datetime.min.time()).replace(hour=hour, minute=minute, tzinfo=JST)
                    end_time = start_time + timedelta(minutes=1)
                else:
                    # Full 1-hour window tracking bracket
                    start_time = datetime.combine(parsed_date, datetime.min.time()).replace(hour=hour, tzinfo=JST)
                    end_time = start_time + timedelta(hours=1)
                
                metrics = PingLog.objects.filter(ts__range=[start_time, end_time], target_id=1).aggregate(Avg('rtt_ms'))
                avg_val = metrics['rtt_ms__avg']
                if avg_val: db_result = f"Average RTT: {avg_val:.2f} ms"

            # 3. Final Synthesis step: Feed data results back to local LLM to generate user natural language
            synthesis_prompt = f"""
            User Question: {user_question}
            Database Query Metrics Result: {db_result}
            Target Window: {target_date_str}
            
            Synthesize a short, direct operational summary response. 
            If the question is in Japanese, respond in Japanese. If in English, respond in English.
            """
            final_res = ollama.generate(model='llama3', prompt=synthesis_prompt)
            
            return Response({"answer": final_res['response'].strip()})

        except Exception as e:
            print(f"Agent Pipeline Failure: {str(e)}")
            return Response({"answer": "I don't know. (Internal handling discrepancy)"})
