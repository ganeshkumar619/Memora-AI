@echo off
REM ====================================================================
REM Starts MEMORA AI backend (port 8000) and frontend (port 5173).
REM ====================================================================
start "MEMORA AI Backend" cmd /k "cd backend && (if not exist .venv (python -m venv .venv || py -m venv .venv)) && call .venv\Scripts\activate.bat && python -m pip install -r requirements.txt && python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload"
start "MEMORA AI Frontend" cmd /k "cd frontend && npm install && npm run dev"
echo ====================================================================
echo MEMORA AI is launching!
echo Backend API: http://127.0.0.1:8000
echo Frontend UI: http://localhost:5173
echo Open http://localhost:5173 in Chrome or Edge for voice input and speech synthesis.
echo ====================================================================
