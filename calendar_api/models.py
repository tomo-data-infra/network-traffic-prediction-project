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

class PingLog(models.Model):
    # Django usually wants a single primary key. 
    # For a composite key (ts, target_id), 'managed=False' handles the queries correctly.
    ts = models.DateTimeField(primary_key=True) 
    target_id = models.IntegerField()
    seq = models.IntegerField(null=True)
    rtt_ms = models.FloatField(null=True)
    is_timeout = models.BooleanField()

    class Meta:
        managed = False # Django won't try to create/delete this table
        db_table = 'ping_logs'
        unique_together = (('ts', 'target_id'),)

class Target(models.Model):
    id = models.AutoField(primary_key=True)
    ip = models.TextField(unique=True)
    label = models.TextField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'targets'

    def __str__(self):
        return self.label or self.ip