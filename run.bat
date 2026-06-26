@echo off
echo ===================================================
echo Starting Smart Solar Plug (Hybrid MQTT/Firebase)
echo ===================================================

echo [0/3] Killing any old backend on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo Killing PID %%a
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

echo [1/3] Installing/Verifying Dependencies...
call venv\Scripts\activate.bat
cd backend
pip install -r requirements.txt -q
cd ..

echo [2/3] Starting FastAPI Backend...
start "Smart Solar Plug Backend" cmd /k "call venv\Scripts\activate.bat && cd backend && uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

echo [3/3] Starting Frontend Server...
start "Smart Solar Plug Frontend" cmd /k "call venv\Scripts\activate.bat && cd frontend && python -m http.server 8080"

echo Opening Frontend in Browser...
timeout /t 4 /nobreak >nul
start "" "http://localhost:8080"

echo Both backend and frontend have been successfully launched!
echo Dashboard auto-updates every 5 seconds from backend.
