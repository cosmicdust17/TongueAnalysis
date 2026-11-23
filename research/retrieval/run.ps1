param(
    [Parameter(ValueFromRemainingArguments=$true)] [string[]]$PipelineArgs
)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Create research/retrieval/.venv and install requirements.txt first; see README.md.' }
Push-Location -LiteralPath $project
try {
    $env:PYTHONIOENCODING = 'utf-8'
    & $python -m research.retrieval @PipelineArgs
    if ($LASTEXITCODE -ne 0) { throw "Pipeline failed: $LASTEXITCODE" }
} finally { Pop-Location }
