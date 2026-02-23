@echo off
setlocal
cd /d "%~dp0"

echo Starting Labor API on port 8001...
start "" http://localhost:8001/files/cba_search.html
py -m uvicorn api.main:app --reload --port 8001

