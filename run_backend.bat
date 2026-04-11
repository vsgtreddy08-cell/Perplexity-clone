@echo off
setlocal
echo ===========================================
echo Perplexity Clone Backend - Minimal Run
echo ===========================================
echo.

:: We only need fastapi, uvicorn, and requests.
:: These are likely already installed or safe to fast-install.
echo [STEP 1] Checking Core Requirements...
python -m pip install --user fastapi uvicorn requests

echo.
echo [STEP 2] Starting Server...
echo.
python -m uvicorn app:app --host 0.0.0.0 --port 8001 --reload

pause
