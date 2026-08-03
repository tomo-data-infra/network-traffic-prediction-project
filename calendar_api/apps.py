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
        remote_user = getattr(settings, 'REMOTE_GPU_USER', None)
        local_port = getattr(settings, 'LOCAL_FORWARD_PORT', None)
        remote_port = getattr(settings, 'REMOTE_LLM_PORT', None)

        if not remote_host or not remote_user or not local_port or not remote_port:
            logger.info("[SSH Tunnel Bypassed] Remote GPU tunnel settings are not fully configured.")
            return

        target = f"{remote_user}@{remote_host}"
        logger.info("[SSH Tunnel System] Initializing automated background tunnel to %s", target)

        ssh_command = [
            "ssh",
            "-N",
            "-L", f"{local_port}:127.0.0.1:{remote_port}",
            target
        ]

        try:
            tunnel_process = subprocess.Popen(
                ssh_command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            atexit.register(tunnel_process.terminate)
            logger.info(
                "[SSH Tunnel System] Tunnel connection anchored on Local Port %s (PID: %s)",
                local_port, tunnel_process.pid
            )
        except Exception:
            logger.exception("[SSH Tunnel Error] Failed to initialize automated port bridge")