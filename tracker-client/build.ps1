$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

if (-not (Test-Path ".env")) {
    Copy-Item .env.example .env
}

pyinstaller --noconfirm --clean --onefile --noconsole --name hrm-tracker --paths . main.py

Write-Host ""
Write-Host "Tracker executable created at: $root\dist\hrm-tracker.exe"
