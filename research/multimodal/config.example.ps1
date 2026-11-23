# Model service: dot-source use-env.ps1 first. These affect the current shell only.
$env:QWEN_MODEL = 'Qwen/Qwen3-VL-2B-Instruct'
$env:QWEN_MAX_PIXELS = '262144'
$env:QWEN_MAX_NEW_TOKENS = '384'
$env:QWEN_MAX_INPUT_TOKENS = '3072'
# After the first successful download, avoid network checks during local runs:
$env:QWEN_OFFLINE = 'true'
# Main FastAPI application: export these in its own shell before starting.
$env:MODEL_PROVIDER = 'http'
$env:MODEL_BASE_URL = 'http://127.0.0.1:8002'
$env:MULTIMODAL_ENABLED = 'true'
$env:KNOWLEDGE_RETRIEVAL_ENABLED = 'true'
$env:RETRIEVAL_BASE_URL = 'http://127.0.0.1:8010'
$env:RETRIEVAL_TIMEOUT_SECONDS = '3'
$env:MODEL_TIMEOUT_SECONDS = '180'
