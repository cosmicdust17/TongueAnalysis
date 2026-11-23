$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/use-env.ps1"
if (!(Test-Path "$PSScriptRoot/.venv/Scripts/python.exe")) {
    python -m venv "$PSScriptRoot/.venv"
    if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed' }
}
& "$PSScriptRoot/.venv/Scripts/python.exe" -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124 --progress-bar off
if ($LASTEXITCODE -ne 0) { throw 'CUDA PyTorch install failed' }
& "$PSScriptRoot/.venv/Scripts/python.exe" -m pip install -r "$PSScriptRoot/requirements.txt" --progress-bar off
if ($LASTEXITCODE -ne 0) { throw 'Multimodal dependencies install failed' }
