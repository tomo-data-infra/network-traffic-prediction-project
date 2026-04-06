from rest_framework import serializers
from .models import EventSession

class EventSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventSession
        fields = '__all__'
