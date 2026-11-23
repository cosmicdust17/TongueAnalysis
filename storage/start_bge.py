import os
from pathlib import Path
root=Path(__file__).resolve().parents[1]
os.environ.update(RETRIEVAL_BACKEND='local', RETRIEVAL_INDEX_PATH=str(root/'research/retrieval/data/index'),
    RETRIEVAL_EMBEDDING=str(root/'research/retrieval/models/bge-small-zh-v1.5'),
    RETRIEVAL_RERANKER=str(root/'research/retrieval/models/bge-reranker-base'),
    RETRIEVAL_OCR_REVIEW_FILE=str(root/'research/retrieval/data/ocr-review.json'),
    HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_PROGRESS_BARS='1',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',
    PYTHONUTF8='1')
import sys
sys.path.insert(0,str(root))
import uvicorn
uvicorn.run('research.retrieval.service:app',host='127.0.0.1',port=8011,workers=1)
