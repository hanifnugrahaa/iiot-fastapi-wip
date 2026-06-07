#!/bin/bash
# SINERGI IIoT - Render Start Script

echo "Starting SINERGI IIoT Backend & Simulator..."

# Start Simulator in the background
python simulator.py &
SIMULATOR_PID=$!

# Start FastAPI using uvicorn
# On Render, the port is provided via the $PORT environment variable
PORT=${PORT:-8000}
uvicorn main:app --host 0.0.0.0 --port $PORT

# If FastAPI stops, kill simulator
kill $SIMULATOR_PID
