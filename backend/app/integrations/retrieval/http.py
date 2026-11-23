import httpx
import hashlib
import json
from pathlib import Path
from pydantic import BaseModel, Field
from app.core.config import settings

class EvidenceChunk(BaseModel):
    chunk_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=12000)
    source_title: str = Field(min_length=1, max_length=500)
    location: str | dict
    is_demo: bool = False
    retrieval_eligible: bool = True
    ocr_status: str = 'unknown'
    source_review_status: str = 'unreviewed'
    ocr_reviewer: str | None = None
    ocr_reviewed_at: str | None = None

async def retrieve_http(client, symptoms, tongue_features, metrics=None):
    s = settings()
    if not s.knowledge_retrieval_enabled or not s.retrieval_base_url:
        return 'disabled', []
    try:
        response = await client.post(s.retrieval_base_url.rstrip('/') + '/v1/retrieve',
            json={'symptoms': symptoms, 'candidate_count': s.retrieval_candidate_count, 'top_k': 5, 'tongue_features': '；'.join(
                f['value'] for f in tongue_features if f.get('confidence') is not None)},
            timeout=s.retrieval_timeout_seconds)
        response.raise_for_status()
        if metrics is not None:
            metrics.update(response.json().get('timings', {}))
        chunks = [EvidenceChunk.model_validate(c).model_dump() for c in response.json()['evidence']]
        if len(chunks) > 10 or len({c['chunk_id'] for c in chunks}) != len(chunks):
            raise ValueError('Invalid evidence count or duplicate IDs')
        reviews = (json.loads(Path(s.retrieval_review_file).read_text(encoding='utf-8'))
                   if s.retrieval_require_reviewed and Path(s.retrieval_review_file).is_file() else {})
        approved = []
        for c in chunks:
            page = c['location'].get('pdf_page') if isinstance(c['location'], dict) else None
            if not c['retrieval_eligible'] or c['ocr_status'] == 'pending_review' or page in {57,64}:
                continue
            if s.retrieval_require_reviewed:
                record = reviews.get(c['chunk_id'], {})
                identity = hashlib.sha256(json.dumps({k:c[k] for k in ('text','source_title','location')},
                    ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()
                if record.get('status') != 'approved' or record.get('content_sha256') != identity or not record.get('reviewer'):
                    continue
                c.update(source_review_status='approved',ocr_reviewer=record['reviewer'],ocr_reviewed_at=record.get('reviewed_at'))
            approved.append(c)
        chunks = approved
        return ('available' if chunks else 'empty'), chunks
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return 'unavailable', []
