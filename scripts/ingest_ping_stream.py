#!/usr/bin/env python3
"""
ingest_ping_stream.py
- High-frequency, lightweight background ingestion worker.
- Intentionally decoupled from Django to optimize memory consumption and resilience.
"""

import os
import sys
import subprocess
import re
import threading
import time
from datetime import datetime, timedelta, timezone
import psycopg2
from dotenv import load_dotenv

# Resolve paths dynamically relative to the script location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# Secure Target ID Input Verification
if len(sys.argv) < 2:
    print("[ERROR] Target ID argument missing.")
    print("Usage: python scripts/ingest_ping_stream.py <TARGET_ID>")
    sys.exit(1)

try:
    TARGET_ID = int(sys.argv[1])
except ValueError:
    print("[ERROR] Target ID must be an integer.")
    sys.exit(1)

JST = timezone(timedelta(hours=9))

# ---- Database Initialization & Infrastructure Check ----
try:
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")

    # Validate that critical parameters are loaded correctly before connecting
    missing_vars = [var_name for var_name, val in [
        ("DB_NAME", db_name), ("DB_USER", db_user), ("DB_HOST", db_host), ("DB_PORT", db_port)
    ] if not val]

    if missing_vars:
        print(f"[FATAL CONFIG ERROR] Missing required environment variables: {', '.join(missing_vars)}")
        print("Please check that your root '.env' file exists and is configured correctly.")
        sys.exit(1)

    conn = psycopg2.connect(
        dbname=db_name,
        user=db_user,
        password=db_password,
        host=db_host,
        port=db_port
    )
    cur = conn.cursor()
    
    # Securely retrieve the target IP from the table using the ID argument
    cur.execute("SELECT ip FROM targets WHERE id = %s;", (TARGET_ID,))
    result = cur.fetchone()
    if not result:
        print(f"[FATAL] Target ID {TARGET_ID} does not exist in inventory database.")
        sys.exit(1)
        
    TARGET_IP = result[0]
except Exception as e:
    print(f"[FATAL DB CRASH] Connection or Lookup failed: {e}")
    sys.exit(1)

# ---- Logging & Regex Compilation ----
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
TIMESTAMP_STR = datetime.now().strftime("%Y%m%d_%H%M%S")
LOGFILE = os.path.join(LOG_DIR, f"ping_target_id_{TARGET_ID}_{TIMESTAMP_STR}.log")

# Regex for Windows Japanese ping output
re_data = re.compile(
    r"(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})\.\d+\s+"  
    r"(?P<ip>\d+\.\d+\.\d+\.\d+)\s+からの応答: "
    r"バイト数\s*=\s*\d+\s+時間\s*=\s*(?P<rtt>\d+)ms\s+TTL\s*=\s*(?P<ttl>\d+)"
)
re_timeout = re.compile(r"(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})\.\d+.*タイムアウト")

INSERT_SQL = """
INSERT INTO ping_logs (ts, target_id, seq, rtt_ms, is_timeout)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING;
"""

# ---- Thread-Safe Telemetry State ----
seq_counter = 0
buf_rows = []
buf_lock = threading.Lock()

def ts_parse(s):
    return datetime.strptime(s, "%Y/%m/%d %H:%M:%S").replace(tzinfo=JST)

def insert_row(ts, is_timeout, rtt=None):
    global seq_counter
    seq_counter += 1
    row = (ts, TARGET_ID, seq_counter, rtt, is_timeout)

    try:
        cur.execute(INSERT_SQL, row)
        conn.commit()
    except Exception as e:
        print(f"[DB ERROR] Real-time insert failed: {e}. Buffering row.")
        conn.rollback()

        with buf_lock:
            buf_rows.append(row)

# ---- Batch thread for recovering missed rows every 60s ----
def batch_commit_thread():
    while True:
        time.sleep(60)
        with buf_lock:
            if buf_rows:
                for row in buf_rows:
                    try:
                        cur.execute(INSERT_SQL, row)
                    except Exception:
                        pass
                conn.commit()
                buf_rows.clear()

# ---- Run background backup thread ---- 
threading.Thread(target=batch_commit_thread, daemon=True).start()

# ---- Execute ping ----
proc = subprocess.Popen(
    ["ping.exe", "-t", "-l", "32", TARGET_IP],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    encoding="cp932" # Windows Japanese encoding
)

print(f"[*] Starting background ingestion process for Target ID: {TARGET_ID} ({TARGET_IP})")
print(f"[*] Local log file mirror path: {LOGFILE}")

try:
    while True:
        try:
            for line in proc.stdout:
                line = line.strip()
                ts_now = datetime.now(JST).strftime("%Y/%m/%d %H:%M:%S.%f")
                line_ts = f"{ts_now} {line}"

                with open(LOGFILE, "a", encoding="utf-8") as f:
                    f.write(line_ts + "\n")

                m = re_data.search(line_ts)
                if m:
                    ts = ts_parse(m["ts"])
                    ip = m["ip"]
                    rtt = int(m["rtt"])
                    ttl = int(m["ttl"])
                    insert_row(ts, False, rtt=rtt)
                    continue

                m = re_timeout.search(line_ts)
                if m:
                    ts = ts_parse(m["ts"])
                    insert_row(ts, True)
                    continue

        except Exception as e:
            print(f"[PROCESS RUNTIME ERROR] Streaming loop glitch: {e}")
            time.sleep(1)

except KeyboardInterrupt:
    print("Stopping ping ingestion...")

finally:
    proc.terminate()
    cur.close()
    conn.close()
