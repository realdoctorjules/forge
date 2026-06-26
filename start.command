#!/bin/bash
# Double-click this file to start Forge. Keep the window open; close it to stop.
cd "$(dirname "$0")"
echo "Starting Forge…"

# free the ports first so a stale server can't block startup
lsof -ti tcp:8000 | xargs kill -9 2>/dev/null
lsof -ti tcp:5173 | xargs kill -9 2>/dev/null
sleep 1

# backend (CAD engine + API) on http://localhost:8000
( cd backend && .venv/bin/uvicorn app.main:app --port 8000 ) &
# frontend (the app you look at) on http://localhost:5173
( cd frontend && npm run dev ) &

sleep 6
open http://localhost:5173
echo ""
echo "Forge is open in your browser:  http://localhost:5173"
echo "(Keep this Terminal window open. Close it to stop Forge.)"
wait
