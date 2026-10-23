@echo off
REM Starts backend (port 8000) and frontend (port 5173) in two windows.
start "MEMORA backend" cmd /k "cd backend && py -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt && uvicorn main:app --port 8000"
start "MEMORA frontend" cmd /k "cd frontend && npm install && npm run dev"
echo Open http://localhost:5173 in Chrome or Edge.
