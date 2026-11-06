$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.11+ is required."
}

python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e .
if (-not (Test-Path agent.toml)) { Copy-Item agent.example.toml agent.toml }
Write-Host "Installed. Edit agent.toml, then run: .\.venv\Scripts\local-llm-code-auditor.exe --config agent.toml"
