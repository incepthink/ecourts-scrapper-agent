# Starts the RQ scrape worker (Windows SimpleWorker = no fork). Needs Redis up.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = "src"
& "$root\.venv\Scripts\rq.exe" worker -w rq.worker.SimpleWorker --url redis://localhost:6379/0 scrapes
