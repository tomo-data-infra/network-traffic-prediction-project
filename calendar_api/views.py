from django.shortcuts import render

# Create your views here.
from rest_framework import viewsets
from .models import EventSession
from .serializers import EventSessionSerializer

class EventSessionViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows event_sessions to be viewed or edited.
    """
    queryset = EventSession.objects.all()
    # queryset = EventSession.objects.all().order_by('-start_ts')
    serializer_class = EventSessionSerializer
