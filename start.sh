#!/bin/bash
# BongaAI Render Start Script - runs both brain and WhatsApp
echo "Starting BongaAI - Bot Assistant: BongaAI"

# Install python deps (Render does pip install automatically but safe)
pip install -r requirements.txt

# Start Python brain in background on Render's PORT
# Render gives PORT=10000, brain must listen there
uvicorn main:app --host 0.0.0.0 --port $PORT &
BRAIN_PID=$!

echo "Brain started PID $BRAIN_PID on port $PORT, waiting 5s..."
sleep 5

# Start WhatsApp bridge (connects to brain via localhost:PORT)
# Override the brain URL to use same PORT
export BRAIN_URL="http://localhost:$PORT"
node whatsapp_bridge.js

# If node crashes, keep brain alive
wait $BRAIN_PID
