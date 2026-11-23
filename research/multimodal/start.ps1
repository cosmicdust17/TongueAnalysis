param([switch]$UseV2, [string]$Adapter = '', [int]$Port = 8002)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/use-env.ps1"
$projectRoot = (Resolve-Path "$PSScriptRoot/../..").Path
Set-Location $projectRoot
$env:MODEL_MODE = 'qwen'
$env:MODEL_DEVICE = 'cpu'
$env:YOLO_CONFIG_DIR = "$PSScriptRoot/results/yolo-settings"
New-Item -ItemType Directory -Force -Path $env:YOLO_CONFIG_DIR | Out-Null
if ($UseV2) {
    $env:MODEL_WEIGHTS = "$projectRoot/research/results/formal/clean-v2-yolo11n-seed42/weights/best.pt"
    $env:MODEL_DATA_YAML = "$projectRoot/research/datasets/clean_v2/data.yaml"
}
$env:QWEN_ADAPTER = $Adapter
& "$PSScriptRoot/.venv/Scripts/python.exe" -m uvicorn app:app --app-dir model-service --host 127.0.0.1 --port $Port --workers 1
