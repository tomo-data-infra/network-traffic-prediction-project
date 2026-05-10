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
    queryset = PingLog.objects.all()
    serializer_class = PingLogSerializer

class TargetViewSet(viewsets.ModelViewSet):
    queryset = Target.objects.all()
    serializer_class = TargetSerializer

# Add the new APIView for the ML Traffic Monitor
class PingDataView(APIView):
    def get(self, request):
        start_str = request.query_params.get("start")
        end_str = request.query_params.get("end")

        # Fallback to last 60 mins if no range is provided
        now = datetime.now(JST)
        start = datetime.fromisoformat(start_str) if start_str else now - timedelta(minutes=30)
        end = datetime.fromisoformat(end_str) if end_str else now + timedelta(minutes=30)

        # 1. Fetch from ORM
        logs = PingLog.objects.filter(ts__range=[start, end], target_id=1).order_by('ts')
        
        if not logs.exists():
            return Response({"times": [], "features": [], "measured": []})

        # 2. Prepare for features.py
        timestamps = np.array([l.ts for l in logs])
        rtts = np.array([l.rtt_ms if l.rtt_ms is not None else np.nan for l in logs])
        timeouts = np.array([1 if l.is_timeout else 0 for l in logs])

        # 3. Process with ML script
        # Ensure your features.py can handle the JST object
        agg_features, agg_times = features.make_features(timestamps, rtts, timeouts, agg_seconds=60, tz=JST)

        # 4. JSON Response (Must be standard Python types)
        return Response({
            "times": [t.isoformat() for t in agg_times],
            "features": agg_features[:, 0].tolist(), # Convert numpy to list
            "measured": [
                {"ts": l.ts.isoformat(), "rtt": l.rtt_ms} for l in logs
            ]
        })