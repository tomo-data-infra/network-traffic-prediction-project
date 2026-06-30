#!/bin/bash
# Terminate older duplicate ingestion streams to prevent duplicate database writes
pkill -9 -f "ingest_ping_stream.py"

# Lock onto the project root directory
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
cd "$SCRIPT_DIR"

echo "Initializing core database network ingestion channels..."
source venv/bin/activate

# Designate the target ID of the IP address here. 
# Launch your target telemetry workers in the safe background
python scripts/ingest_ping_stream.py 1

# Scale up targets easily here with uncommenting the following line:
# python scripts/ingest_ping_stream.py 2

echo "[SUCCESS] Telemetry background streams are now actively piping data to PostgreSQL."
