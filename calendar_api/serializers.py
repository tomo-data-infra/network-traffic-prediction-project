from rest_framework import serializers
from .models import EventSession, PingLog, Target

class EventSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventSession
        fields = '__all__'

class PingLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = PingLog
        fields = '__all__'

class TargetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Target
        fields = '__all__'