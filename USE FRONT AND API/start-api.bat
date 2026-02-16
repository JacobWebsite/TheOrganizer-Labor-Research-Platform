@echo off
cd /d "C:\Users\jakew\Downloads\labor-data-project"
echo Starting API on http://localhost:8001 ...
py -m uvicorn api.main:app --reload --port 8001
pause
