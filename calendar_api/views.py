from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import EventSession, PingLog, Target
from .serializers import EventSessionSerializer, PingLogSerializer, TargetSerializer
# Import your features script (assuming it's in a utils subfolder)
from .utils import features 
import numpy as np
from datetime import datetime, timedelta, timezone

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
        start = request.query_params.get("start")
        end = request.query_params.get("end")

        # Fetch data using Django ORM
        logs = PingLog.objects.filter(ts__range=[start, end], target_id=1).order_by('ts')
        
        # Convert QuerySet to Numpy for your features.py
        timestamps = np.array([l.ts for l in logs])
        rtts = np.array([l.rtt_ms if l.rtt_ms is not None else np.nan for l in logs])
        timeouts = np.array([1 if l.is_timeout else 0 for l in logs])

        # Run your ML feature logic
        agg_features, agg_times = features.make_features(timestamps, rtts, timeouts, agg_seconds=60, tz=JST)

        return Response({
            "times": [t.isoformat() for t in agg_times],
            "features": agg_features[:, 0].tolist() # RTT Mean
        })