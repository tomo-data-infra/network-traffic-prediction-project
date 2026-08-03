#!/bin/bash

# Dynamically lock onto the root directory where this script sits
PROJECT_ROOT=$(dirname "$(readlink -f "$0")")
cd "$PROJECT_ROOT"

SECURE_ENV="../.env"

# Pull environment configurations manually
if [ -f "$SECURE_ENV" ]; then
    export $(cat "$SECURE_ENV" | grep -v '#' | xargs)
else
    echo "[ERROR] Secure .env file not found."
    exit 1
fi

# Terminate conflicting backend or frontend instances
pkill -9 -f "manage.py"
pkill -9 -f "vite"
pkill -9 -f "ssh -N -L $LOCAL_FORWARD_PORT"

# Start Cube Core container natively in WSL
echo "Starting Containerized Cube Core Semantic Layer..."
cd "$PROJECT_ROOT/cube"
sudo docker compose --env-file ../../.env up -d

# Note: the Remote GPU SSH tunnel is opened automatically by Django on startup
# (calendar_api/apps.py), so it isn't opened here.

# Start Django Backend
echo "Starting Django Backend Server..."
cd "$PROJECT_ROOT"
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "[ERROR] Python Virtual environment folder not found."
    exit 1
fi

python manage.py runserver &

# Start Vite Frontend UI
echo "Starting Vite Frontend UI..."
cd "$PROJECT_ROOT"

if [ -d "network-ui" ]; then
    cd network-ui
    npm run dev
else
    echo "[ERROR] 'network-ui' folder not found."
    exit 1
fi
