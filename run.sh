#!/usr/bin/env bash
# Start SAGE: Flask backend + Streamlit frontend
# Requires: Ollama running at localhost:11434
#           (optional) .env file with GROQ_API_KEY

set -e

cd "$(dirname "$0")"

mkdir -p sage_state

echo "Starting Flask backend on port 8000..."
python backend.py &
BACKEND_PID=$!

sleep 1

echo "Starting Streamlit frontend..."
streamlit run app.py --server.port 8501 &
FRONTEND_PID=$!

echo ""
echo "SAGE is running:"
echo "  Frontend: http://localhost:8501"
echo "  Backend:  http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop both."

cleanup() {
    echo ""
    echo "Shutting down..."
    kill $FRONTEND_PID 2>/dev/null
    kill $BACKEND_PID 2>/dev/null
    wait $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID 2>/dev/null
    echo "Done."
}

trap cleanup INT TERM

wait
