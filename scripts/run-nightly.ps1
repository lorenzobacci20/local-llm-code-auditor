param(
  [string]$ProjectPath = (Split-Path -Parent $PSScriptRoot),
  [string]$ConfigPath = "",
  [string]$Model = "qwen3.5:9b",
  [int]$NumCtx = 65536,
  [int]$NumPredict = 8192,
  [string]$OllamaPath = "",
  [int]$LogRetentionDays = 30
)

$ErrorActionPreference = "Stop"
$ProjectPath = (Resolve-Path $ProjectPath).Path
if ([string]::IsNullOrWhiteSpace($ConfigPath)) { $ConfigPath = Join-Path $ProjectPath "agent.toml" }
$ConfigPath = (Resolve-Path $ConfigPath).Path
$exe = Join-Path $ProjectPath ".venv\Scripts\local-llm-code-auditor.exe"
if (-not (Test-Path $exe -PathType Leaf)) { throw "Local LLM Code Auditor executable not found: $exe" }

$logDir = Join-Path $ProjectPath "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$cutoff = (Get-Date).AddDays(-[Math]::Abs($LogRetentionDays))
Get-ChildItem $logDir -Filter "nightly-*.log" -File -ErrorAction SilentlyContinue | Where-Object LastWriteTime -lt $cutoff | Remove-Item -Force -ErrorAction SilentlyContinue
$stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$logPath = Join-Path $logDir "nightly-$stamp.log"

function Write-NightlyLog([string]$Message) {
  $line = "[{0}] {1}" -f (Get-Date -Format "s"), $Message
  $line | Tee-Object -FilePath $logPath -Append
}

try {
  Write-NightlyLog "Starting Local LLM Code Auditor nightly run."
  Write-NightlyLog "User=$([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) PID=$PID"
  Write-NightlyLog "ProjectPath=$ProjectPath"
  Write-NightlyLog "ConfigPath=$ConfigPath"
  Write-NightlyLog "Model=$Model NumCtx=$NumCtx NumPredict=$NumPredict"

  if ([string]::IsNullOrWhiteSpace($OllamaPath)) {
    $ollama = Get-Command "ollama.exe" -ErrorAction SilentlyContinue
    if (-not $ollama) { $ollama = Get-Command "ollama" -ErrorAction SilentlyContinue }
    if (-not $ollama) { throw "Ollama executable was not found in PATH." }
    $OllamaPath = $ollama.Source
  }
  else {
    $OllamaPath = (Resolve-Path $OllamaPath).Path
  }

  if (-not (Test-Path $OllamaPath -PathType Leaf)) { throw "Ollama executable not found: $OllamaPath" }
  Write-NightlyLog "OllamaPath=$OllamaPath"

  & $OllamaPath list *> $null
  if ($LASTEXITCODE -ne 0) {
    Write-NightlyLog "Ollama is not responding; starting 'ollama serve'."
    Start-Process -FilePath $OllamaPath -ArgumentList "serve" -WindowStyle Hidden | Out-Null
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
      Start-Sleep -Seconds 1
      & $OllamaPath list *> $null
      if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    }
    if (-not $ready) { throw "Ollama did not become ready within 30 seconds." }
  }

  & $OllamaPath show $Model *> $null
  if ($LASTEXITCODE -ne 0) { throw "Nightly model '$Model' is not installed." }

  $agentArgs = @("--config", $ConfigPath, "--model", $Model, "--num-ctx", "$NumCtx", "--num-predict", "$NumPredict")
  Push-Location $ProjectPath
  try {
    & $exe @agentArgs 2>&1 | Tee-Object -FilePath $logPath -Append
    $agentExitCode = $LASTEXITCODE
  }
  finally { Pop-Location }

  Write-NightlyLog "Local LLM Code Auditor process finished with exit code $agentExitCode."

  if ($agentExitCode -eq 0) {
    Write-NightlyLog "Scheduler status=CLEAN_AUDIT."
    exit 0
  }

  if ($agentExitCode -eq 1) {
    Write-NightlyLog "Scheduler status=AUDIT_COMPLETED_WITH_FINDINGS. Reports contain one or more actionable findings; scheduler infrastructure succeeded."
    exit 0
  }

  Write-NightlyLog "Scheduler status=AGENT_OPERATIONAL_ERROR."
  exit $agentExitCode
}
catch {
  Write-NightlyLog "Scheduler status=INFRASTRUCTURE_ERROR."
  Write-NightlyLog ("ERROR: " + $_.Exception.ToString())
  exit 10
}
