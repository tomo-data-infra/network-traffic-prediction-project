import os
import subprocess
import atexit
import logging
from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger(__name__)

class CalendarApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'calendar_api'

    def ready(self):
        if os.environ.get('RUN_MAIN') != 'true':
            return

        remote_host = getattr(settings, 'REMOTE_GPU_SERVER_IP', None)
        if not remote_host:
            logger.info("[SSH Tunnel Bypassed] REMOTE_GPU_SERVER_IP is not set.")
            return

        logger.info("[SSH Tunnel System] Initializing automated background tunnel to %s", remote_host)

        ssh_command = [
            "ssh",
            "-N",
            "-L", "8080:127.0.0.1:11434",
            remote_host
        ]

        try:
            tunnel_process = subprocess.Popen(
                ssh_command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            atexit.register(tunnel_process.terminate)
            logger.info(
                "[SSH Tunnel System] Tunnel connection anchored on Local Port 8080 (PID: %s)",
                tunnel_process.pid
            )
        except Exception:
            logger.exception("[SSH Tunnel Error] Failed to initialize automated port bridge")