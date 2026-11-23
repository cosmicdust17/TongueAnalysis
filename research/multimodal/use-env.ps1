$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/../use-e-storage.ps1"
$env:HF_HOME = 'E:\CodexData\cache\tongue-analysis\huggingface'
$env:TORCH_HOME = 'E:\CodexData\cache\tongue-analysis\torch'
$env:PYTHONUTF8 = '1'
$env:HF_HUB_DISABLE_XET = '1'
New-Item -ItemType Directory -Force -Path $env:HF_HOME, $env:TORCH_HOME | Out-Null
