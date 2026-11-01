# Start the development backend on port 8001 against oak_binder_test, with the local store (never
# the Google Drive vault) and the Spine and WorkMind doubles served by tests.local_stubs
# (acceptance audit, D40). Reads OAK_TEST_APP_DATABASE_URL from backend\.env and uses it
# as the application database; prints no value from .env. Everything else in .env still applies.
#
#   powershell -NoProfile -File scripts\dev_backend_with_doubles.ps1
#
# Start the doubles first:  backend\.venv\Scripts\python.exe -m tests.local_stubs
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location (Join-Path $root "backend")

$line = Get-Content ".env" | Where-Object { $_ -match "^OAK_TEST_APP_DATABASE_URL=" } | Select-Object -First 1
if (-not $line) { throw "backend\.env has no OAK_TEST_APP_DATABASE_URL; refusing to guess a database" }
$url = $line.Substring("OAK_TEST_APP_DATABASE_URL=".Length).Trim()
if ($url -notmatch "/oak_binder_test(\?|$)") { throw "OAK_TEST_APP_DATABASE_URL does not name oak_binder_test; refusing" }

$env:OAK_DATABASE_URL = $url
$env:OAK_STORE = "local"
$env:OAK_ATTACHMENTS_DIR = Join-Path $root "var\attachments-browser-check"
$env:OAK_SPINE_URL = "http://127.0.0.1:8010"
$env:OAK_WORKMIND_URL = "http://127.0.0.1:8012"
New-Item -ItemType Directory -Force $env:OAK_ATTACHMENTS_DIR | Out-Null
Write-Host "Backend on 8001 · database oak_binder_test · store local ($env:OAK_ATTACHMENTS_DIR) · Spine double 8010 · WorkMind double 8012"
& ".venv\Scripts\python.exe" -m uvicorn oak_binder.main:create_app --factory --port 8001
