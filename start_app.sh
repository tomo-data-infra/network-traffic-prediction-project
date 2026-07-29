#!/bin/bash

# Terminate conflicting backend or frontend instances
pkill -9 -f "manage.py"
pkill -9 -f "vite"
pkill -9 -f "ssh -N -L 8080"

# Dynamically lock onto the root directory where this script sits
PROJECT_ROOT=$(dirname "$(readlink -f "$0")")
cd "$PROJECT_ROOT"

# Pull environment configurations manually
if [ -f ".env" ]; then
    export $(cat .env | grep -v '#' | xargs)
else
    echo "[ERROR] Main .env file not found."
    exit 1
fi

# Start Cube Core container natively in WSL
echo "Starting Containerized Cube Core Semantic Layer..."
cd "$PROJECT_ROOT/cube"
sudo docker compose --env-file ../.env up -d

# Initialize Secure Remote GPU Server SSH Network Tunnel
echo "Opening Private Remote GPU Tunnel on Local Port $LOCAL_FORWARD_PORT..."
# ssh -f -N -L $LOCAL_FORWARD_PORT:127.0.0.1:$REMOTE_LLM_PORT user@$REMOTE_GPU_SERVER_IP
ssh -f -N -L $LOCAL_FORWARD_PORT:127.0.0.1:$REMOTE_LLM_PORT ${REMOTE_GPU_USER}@${REMOTE_GPU_SERVER_IP}


# Check if Docker failed, but force directory reset regardless
#if [ $? -ne 0 ]; then
#    echo "Docker Compose hit a warning/error, continuing system boot..."
#fi


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
