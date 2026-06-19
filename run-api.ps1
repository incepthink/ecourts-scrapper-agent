# Starts the FastAPI backend on http://localhost:8000 (uses the repo .venv).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = "src"
& "$root\.venv\Scripts\uvicorn.exe" api:app --reload --port 8000
