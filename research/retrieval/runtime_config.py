"""Configuration for reproducible local acceptance commands; never prints credentials."""
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent


def configure():
    from dotenv import dotenv_values
    # Only the pre-existing database password is reused; no main application configuration is changed.
    main_env = dotenv_values(ROOT/'.env')
    os.environ.setdefault('NEO4J_URI', 'bolt://127.0.0.1:17687')
    os.environ.setdefault('NEO4J_USER', 'neo4j')
    if not os.getenv('NEO4J_PASSWORD'):
        os.environ['NEO4J_PASSWORD'] = main_env['NEO4J_PASSWORD']
    os.environ.setdefault('RETRIEVAL_NEO4J_DATABASE', 'neo4j')
    os.environ.setdefault('RETRIEVAL_BACKEND', 'neo4j')
    os.environ.setdefault('RETRIEVAL_INDEX_ID', '8b63aa40026e070b33e62d0b')
    os.environ.setdefault('RETRIEVAL_EMBEDDING', str(BASE/'models/bge-small-zh-v1.5'))
    os.environ.setdefault('RETRIEVAL_RERANKER', str(BASE/'models/bge-reranker-base'))
    os.environ.setdefault('RETRIEVAL_REVIEW_FILE', str(BASE/'data/qwen-batch/candidates.jsonl'))
    os.environ.setdefault('RETRIEVAL_OCR_REVIEW_FILE', str(BASE/'data/ocr-review.json'))
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
    os.environ.setdefault('HF_HUB_DISABLE_PROGRESS_BARS', '1')
    os.environ.setdefault('OMP_NUM_THREADS', '4')
    os.environ.setdefault('MKL_NUM_THREADS', '4')
    token_path = BASE/'data/admin-token.txt'
    token_path.parent.mkdir(parents=True, exist_ok=True)
    if not token_path.exists():
        token_path.write_text(secrets.token_urlsafe(32), encoding='utf-8')
    os.environ.setdefault('RETRIEVAL_ADMIN_TOKEN', token_path.read_text(encoding='utf-8').strip())
