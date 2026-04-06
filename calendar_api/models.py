from django.db import models

class EventSession(models.Model):
    # Mapping the enum type 'event_type' to Django choices
    class EventType(models.TextChoices):
        # Add your actual PostgreSQL enum values here
        VIDEO = 'video_session', 'Video Session'
        SYSTEM = 'system_update', 'System Update'

    session_id = models.AutoField(primary_key=True)
    start_ts = models.DateTimeField()
    end_ts = models.DateTimeField()
    event_name = models.CharField(max_length=100, null=True, blank=True)
    expected_devices = models.IntegerField(default=1)
    session_category = models.CharField(
        max_length=50, 
        choices=EventType.choices
    )

    class Meta:
        db_table = 'event_sessions'  # Directs Django to your specific table
        managed = False              # Django won't try to create/delete this table

