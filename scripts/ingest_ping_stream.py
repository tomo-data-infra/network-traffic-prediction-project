#!/usr/bin/env python3
"""
ping_ingest_hybrid.py
- Execute ping in Python (Windows)
- Real-time ingestion to PostgreSQL
- Simultaneous log file output
- Lightweight batch to recover missed rows every 1 min
"""

import subprocess
import re
from datetime import datetime, timedelta, timezone
import psycopg2
import threading
import time
import os

# ---- Settings ----
TARGET = "192.168.200.1"

DSN = "dbname=log_collector user=postgres host=127.0.0.1"
LOG_DIR = "/mnt/c/Users/user/Documents/projects/ping_rtt_prediction/logs"
LOGFILE = os.path.join(LOG_DIR, f"ping_log_{TARGET}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
JST = timezone(timedelta(hours=9))

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Regex for Windows Japanese ping output
re_data = re.compile(
    r"(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})\.\d+\s+"  
    r"(?P<ip>\d+\.\d+\.\d+\.\d+)\s+からの応答: "
    r"バイト数\s*=\s*\d+\s+時間\s*=\s*(?P<rtt>\d+)ms\s+TTL\s*=\s*(?P<ttl>\d+)"
)
re_timeout = re.compile(r"(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})\.\d+.*タイムアウト")

# ---- DB setup ----
conn = psycopg2.connect(DSN)
cur = conn.cursor()

insert_sql = """
INSERT INTO ping_logs (ts, target_id, seq, rtt_ms, is_timeout)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING;
"""

# ---- State ----
target_id = None
seq_counter = 0
buf_rows = []
buf_lock = threading.Lock()  # for thread-safe batch commit

def ts_parse(s):
    return datetime.strptime(s, "%Y/%m/%d %H:%M:%S").replace(tzinfo=JST)

def get_target_id(ip):
    cur.execute("""
        INSERT INTO targets (ip) VALUES (%s)
        ON CONFLICT (ip) DO UPDATE SET ip = EXCLUDED.ip
        RETURNING id;
    """, (ip,))
    return cur.fetchone()[0]

def insert_row(ts, is_timeout, ip=None, rtt=None, ttl=None):
    global target_id, seq_counter
    if target_id is None and ip is not None:
        target_id = get_target_id(ip)
    seq_counter += 1
    row = (ts, target_id, seq_counter, rtt, is_timeout)
    
    # Add to buffer
    with buf_lock:
        buf_rows.append(row)

    # Real-time commit immediately
    try:
        cur.execute(insert_sql, row)
        conn.commit()
    except Exception as e:
        print(f"[DB ERROR] {e}, buffering row for retry")

# ---- Batch thread for recovering missed rows every 60s ----
def batch_commit_thread():
    while True:
        time.sleep(60)  # 1-minute interval
        with buf_lock:
            if buf_rows:
                # print(f"[BATCH] Committing {len(buf_rows)} buffered rows")
                for row in buf_rows:
                    try:
                        cur.execute(insert_sql, row)
                    except Exception as e:
                        print(f"[BATCH DB ERROR] {e}")
                conn.commit()
                buf_rows.clear()

# Start batch thread
threading.Thread(target=batch_commit_thread, daemon=True).start()

# ---- Execute ping ----
proc = subprocess.Popen(
    ["ping.exe", "-t", "-l", "32", TARGET],  # -t = continuous ping, -l 32 = packet size 32 bytes
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    encoding="cp932" # Windows Japanese encoding
)

print(f"Starting hybrid ping ingestion for {TARGET}...")
print(f"Log file: {LOGFILE}")

try:
    while True:
        try:
            # Read ping output line by line
            for line in proc.stdout:
                line = line.strip()
                ts_now = datetime.now(JST).strftime("%Y/%m/%d %H:%M:%S.%f")
                line_ts = f"{ts_now} {line}"

                # Write to log file
                with open(LOGFILE, "a", encoding="utf-8") as f:
                    f.write(line_ts + "\n")

                # Parse normal response
                m = re_data.search(line_ts)
                if m:
                    ts = ts_parse(m["ts"])
                    ip = m["ip"]
                    rtt = int(m["rtt"])
                    ttl = int(m["ttl"])
                    insert_row(ts, False, ip=ip, rtt=rtt, ttl=ttl)
                    # print(f"[OK] {ts} {ip} {rtt}ms TTL={ttl}")
                    continue

                # Parse timeout
                m = re_timeout.search(line_ts)
                if m:
                    ts = ts_parse(m["ts"])
                    insert_row(ts, True)
                    # print(f"[TIMEOUT] {ts}")
                    continue

        except Exception as e:
            # Log any unexpected errors and retry after 1 sec
            log_error(e)
            time.sleep(1)

except KeyboardInterrupt:
    print("Stopping ping ingestion...")

finally:
    proc.terminate()
    cur.close()
    conn.close()
