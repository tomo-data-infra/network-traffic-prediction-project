#!/bin/bash

# Terminate conflicting backend or frontend instances
pkill -9 -f "manage.py"
pkill -9 -f "vite"

# Dynamically lock onto the root directory where this script sits
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
cd "$SCRIPT_DIR"

# Start Django in the background
echo "Starting Django Backend..."
source venv/bin/activate
python manage.py runserver & 

# Move to the network-ui directory
cd network-ui

# Start Vite
echo "Starting Vite Frontend..."

npm run dev
