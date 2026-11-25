param(
    [ValidateSet('Neo4j','Ingest','Extract','Serve','Verify','TestPublication','Publish')]
    [string]$Action = 'Verify',
    [int]$Limit = 12,
    [string]$ReviewWorkbook,
    [string]$ReviewFile,
    [int]$Port = 8011,
    [switch]$GraphOnly
)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
Push-Location -LiteralPath $project
try {
    $env:PYTHONIOENCODING = 'utf-8'
    switch ($Action) {
        'Neo4j' {
            & $python -c "import os,subprocess; from research.retrieval.runtime_config import configure; configure(); subprocess.run(['docker','compose','-p','tongue-retrieval','-f','research/retrieval/compose.yaml','up','-d'],check=True)"
        }
        'Ingest' { & $python -m research.retrieval.acceptance ingest }
        'Extract' {
            . (Join-Path $project 'research\multimodal\use-env.ps1')
            $env:QWEN_OFFLINE = 'true'
            $env:HF_HUB_OFFLINE = '1'
            $env:TRANSFORMERS_OFFLINE = '1'
            $env:HF_HUB_DISABLE_PROGRESS_BARS = '1'
            & (Join-Path $project 'research\multimodal\.venv\Scripts\python.exe') -m research.retrieval.extract_batch --limit $Limit
        }
        'Serve' {
            if ($GraphOnly) {
                & $python -m research.retrieval.serve --port $Port --graph-only
            } else {
                & $python -m research.retrieval.serve --port $Port
            }
        }
        'Verify' { & $python -m research.retrieval.acceptance http --base-url "http://127.0.0.1:$Port" }
        'TestPublication' { & $python -m research.retrieval.acceptance test-graph }
        'Publish' {
            if ($ReviewWorkbook) {
                if ($ReviewFile) {
                    & $python -m research.retrieval.workbook_review $ReviewWorkbook --review-file $ReviewFile
                } else {
                    & $python -m research.retrieval.workbook_review $ReviewWorkbook
                }
                if ($LASTEXITCODE -ne 0) { throw '审核表未通过校验，发布已停止' }
            }
            if ($ReviewFile) {
                & $python -m research.retrieval.acceptance publish --review-file $ReviewFile
            } else {
                & $python -m research.retrieval.acceptance publish
            }
        }
    }
    if ($LASTEXITCODE -ne 0) { throw "Action failed: $LASTEXITCODE" }
} finally { Pop-Location }
