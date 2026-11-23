# Dot-source this file before installation or training in a new PowerShell session.
$env:PIP_CACHE_DIR = 'E:\CodexData\cache\tongue-analysis\pip'
$env:TEMP = 'E:\CodexData\cache\tongue-analysis\temp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:PIP_CACHE_DIR, $env:TEMP | Out-Null
Write-Host 'Dependency cache and temporary storage are on drive E.'
