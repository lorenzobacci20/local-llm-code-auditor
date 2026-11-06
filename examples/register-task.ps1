param(
  [string]$ProjectPath = (Split-Path -Parent $PSScriptRoot),
  [string]$At = "02:00",
  [string]$Model = "qwen3.5:9b",
  [int]$NumCtx = 65536,
  [int]$NumPredict = 8192,
  [string]$TaskName = "Local LLM Code Auditor Nightly"
)

$ErrorActionPreference = "Stop"
$ProjectPath = (Resolve-Path $ProjectPath).Path
$runner = Join-Path $ProjectPath "scripts\run-nightly.ps1"
$config = Join-Path $ProjectPath "agent.toml"
if (-not (Test-Path $runner -PathType Leaf)) { throw "Nightly runner not found: $runner" }
if (-not (Test-Path $config -PathType Leaf)) { throw "Config not found: $config" }

$ollama = Get-Command "ollama.exe" -ErrorAction SilentlyContinue
if (-not $ollama) { $ollama = Get-Command "ollama" -ErrorAction SilentlyContinue }
if (-not $ollama) { throw "Ollama executable was not found in PATH." }
$ollamaPath = $ollama.Source
& $ollamaPath show $Model *> $null
if ($LASTEXITCODE -ne 0) { throw "Nightly model '$Model' is not installed. Run: ollama pull $Model" }

$argument = @(
  "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
  "-File", "`"$runner`"", "-ProjectPath", "`"$ProjectPath`"",
  "-ConfigPath", "`"$config`"", "-Model", "`"$Model`"",
  "-NumCtx", "$NumCtx", "-NumPredict", "$NumPredict",
  "-OllamaPath", "`"$ollamaPath`""
) -join " "

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argument -WorkingDirectory $ProjectPath
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 10) -MultipleInstances IgnoreNew
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Local LLM Code Auditor nightly audit across configured Git roots using local Ollama." -Force | Out-Null

Write-Host "Registered '$TaskName' for $At using model '$Model' with context $NumCtx."
Write-Host "Ollama pinned to: $ollamaPath"
Write-Host "The task uses the current interactive user, starts when available after a missed trigger, wakes the PC when possible, and ignores overlapping runs."
Write-Host "Audit findings do not mark Scheduler infrastructure as failed; true runtime/configuration failures still return non-zero."
Write-Host "Logs: $(Join-Path $ProjectPath 'logs\nightly-*.log')"
