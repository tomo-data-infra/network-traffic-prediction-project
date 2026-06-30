from django.contrib import admin
from .models import EventSession, PingLog, Target, AIAgentLog

# Registering models makes them viewable/editable in the Django Admin
admin.site.register(EventSession)
admin.site.register(PingLog)
admin.site.register(Target)
admin.site.register(AIAgentLog)