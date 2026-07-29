import os
import subprocess
import atexit
from django.apps import AppConfig
from django.conf import settings

class CalendarApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'calendar_api'

    def ready(self):
        # Prevent double-execution when Django runs its file-reloader process thread
        if os.environ.get('RUN_MAIN') == 'true':
            # Safely check if a Remote Server IP or explicit Alias is configured
            remote_host = getattr(settings, 'REMOTE_GPU_SERVER_IP', None)
            if not remote_host:
                print("[SSH Tunnel Bypassed] Bypassed: REMOTE_GPU_SERVER_IP is not set.")
                return

            print(f"[SSH Tunnel System] Initializing automated background tunnel to {remote_host}...")
            
            # Formulate the background OpenSSH execution command matrix
            # Uses your system's native SSH configuration profile keys automatically
            ssh_command = [
                "ssh", 
                "-N", 
                "-L", "8080:127.0.0.1:11434", 
                remote_host
            ]
            
            try:
                # Launch the SSH tunnel silently as an independent background daemon subprocess
                # stdout/stderr are redirected to DEVNULL so it never opens a visible terminal window cluttering your workspace
                tunnel_process = subprocess.Popen(
                    ssh_command, 
                    stdout=subprocess.DEVNULL, 
                    stderr=subprocess.DEVNULL
                )
                
                # Register a hook to automatically terminate the background tunnel process when Django shuts down
                atexit.register(tunnel_process.terminate)
                print(f"[SSH Tunnel System] Tunnel connection safely anchored on Local Port 8080 (PID: {tunnel_process.pid})")
                
            except Exception as e:
                print(f"[SSH Tunnel Error] Failed to initialize automated port bridge: {str(e)}")