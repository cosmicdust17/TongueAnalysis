param([Parameter(Mandatory=$true)][int[]]$ProcessIds)
$ErrorActionPreference='Stop'
Set-Location (Resolve-Path "$PSScriptRoot/../..").Path
. "$PSScriptRoot/use-env.ps1"
$out="$PSScriptRoot/results/fissure-regression"
New-Item -ItemType Directory -Force -Path $out | Out-Null
foreach ($processNumber in $ProcessIds) {
    $processRecord=Get-CimInstance Win32_Process -Filter "ProcessId=$processNumber" -ErrorAction SilentlyContinue
    if ($processRecord -and $processRecord.CommandLine -match 'uvicorn app.main:app|uvicorn app:app|storage/start_bge.py') { Stop-Process -Id $processNumber -Force }
}
$env:MODEL_MODE='qwen'
$env:QWEN_MAX_NEW_TOKENS='256'
$env:QWEN_OFFLINE='true'
Start-Process research/multimodal/.venv/Scripts/python.exe -WindowStyle Hidden -ArgumentList '-m uvicorn app:app --app-dir model-service --host 127.0.0.1 --port 8002 --workers 1' -RedirectStandardOutput "$out/model.stdout.log" -RedirectStandardError "$out/model.stderr.log"
Start-Process research/retrieval/.venv/Scripts/python.exe -WindowStyle Hidden -ArgumentList 'storage/start_bge.py' -RedirectStandardOutput "$out/retrieval.stdout.log" -RedirectStandardError "$out/retrieval.stderr.log"
Start-Process .venv/Scripts/python.exe -WindowStyle Hidden -ArgumentList '-m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --no-access-log' -RedirectStandardOutput "$out/backend.stdout.log" -RedirectStandardError "$out/backend.stderr.log"
