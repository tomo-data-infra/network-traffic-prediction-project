#!/bin/bash

# Terminate conflicting backend or frontend instances
pkill -9 -f "manage.py"
pkill -9 -f "vite"

# Dynamically lock onto the root directory where this script sits
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
cd "$SCRIPT_DIR"

# Start Django Backend
echo "Starting Django Backend Server..."
source venv/bin/activate
python manage.py runserver > /dev/null 2>&1 & 

# Start Vite Frontend UI
echo "Starting Vite Frontend UI..."
if [ -d "network-ui" ]; then
    cd network-ui
    npm run dev
else
    echo "[ERROR] 'network-ui' folder not found."
    exit 1
fi
