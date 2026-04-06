#!/bin/bash

# Kill any old Django/Vite processes first
pkill -9 -f "manage.py"
pkill -9 -f "vite"

# Get the directory where THIS script is located
# /mnt/c/Users/user/Documents/projects/ping_rtt_prediction
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")

# Move to the Parent Directory (the main project folder)
cd "$SCRIPT_DIR/.."

# Start Django in the background
echo "Starting Django Backend..."
source venv/bin/activate
python manage.py runserver & 

# Move to the network-ui directory
cd network-ui

# Start Vite
echo "Starting Vite Frontend..."

npm run dev
