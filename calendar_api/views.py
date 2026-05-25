from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import EventSession, PingLog, Target
from .serializers import EventSessionSerializer, PingLogSerializer, TargetSerializer
# Import your features script (assuming it's in a utils subfolder)
from .utils import features 
import numpy as np
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
        
        # 3. Fetch ONLY the requested slice  Fetch Network Telemetry
        logs = PingLog.objects.filter(ts__range=[start, end], target_id=1).order_by('ts')
        
        # --- CRITICAL MISSING BLOCK START ---
        # Force explicit types to ensure empty dataframes do not cause out-of-bounds array crashes
        timestamps = np.array([l.ts for l in logs], dtype=object)
        rtts = np.array([l.rtt_ms if l.rtt_ms is not None else np.nan for l in logs], dtype=float)
        timeouts = np.array([1 if l.is_timeout else 0 for l in logs], dtype=int)
        # --- CRITICAL MISSING BLOCK END ---

        # 4. ML Processing for that specific window
        agg_features, agg_times = features.make_features(
            timestamps, 
            rtts, 
            timeouts, 
            agg_seconds=60, 
            tz=JST, 
            start_window=start, 
            end_window=end
        )

        # 4. Return the JSON package
        # FETCH OVERLAPPING CALENDAR EVENTS FOR THIS VISUAL WINDOW
        # If an event starts before the window ends, and ends after the window starts, it overlaps.
        overlapping_events = EventSession.objects.filter(
            start_ts__lt=end,
            end_ts__gt=start
        ).order_by('start_ts')

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
            "events": events_payload # Forwarded payload for the concurrent timeline track
        })
