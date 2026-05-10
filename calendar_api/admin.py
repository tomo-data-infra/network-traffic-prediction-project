from django.contrib import admin
from .models import EventSession, PingLog, Target

# Registering models makes them viewable/editable in the Django Admin
admin.site.register(EventSession)
admin.site.register(PingLog)
admin.site.register(Target)