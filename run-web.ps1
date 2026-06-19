# Starts the Next.js frontend on http://localhost:3000.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location "$root\web"
npm run dev
