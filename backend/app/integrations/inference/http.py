from pathlib import Path
import json
from time import perf_counter
from uuid import uuid5, NAMESPACE_URL
import httpx
from app.core.config import settings
from .schemas import ModelResult
from pydantic import BaseModel, ConfigDict, Field

class GeneratedOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    symptoms_summary: str = Field(max_length=600)
    analysis: str = Field(min_length=1, max_length=1600)
    cited_chunk_ids: list[str] = Field(max_length=10)
    pending_observations: list[str] = Field(default_factory=list, max_length=10)

class HttpAdapter:
    async def analyze(self, image_path: str, symptoms: str) -> ModelResult:
        s = settings()
        headers = {'Authorization': f'Bearer {s.model_api_key}'} if s.model_api_key else {}
        async with httpx.AsyncClient(timeout=s.model_timeout_seconds, trust_env=False) as client:
            metrics, detected = {}, None
            chunks, evidence_status = [], 'disabled'
            if s.multimodal_enabled:
                started = perf_counter()
                with Path(image_path).open('rb') as image:
                    detection = await client.post(s.model_base_url.rstrip('/') + '/v1/detect',
                        files={'image': ('tongue.jpg', image, 'image/jpeg')}, headers=headers)
                detection.raise_for_status()
                detected = ModelResult.model_validate(detection.json())
                metrics['yolo_seconds'] = perf_counter() - started
                from app.integrations.retrieval.http import retrieve_http
                started = perf_counter()
                evidence_status, chunks = await retrieve_http(client, symptoms,
                    [f.model_dump() for f in detected.tongue_features], metrics)
                metrics['bge_seconds'] = perf_counter() - started
            with Path(image_path).open('rb') as image:
                response = await client.post(s.model_base_url.rstrip('/') + '/v1/infer',
                    files={'image': ('tongue.jpg', image, 'image/jpeg')},
                    data={'symptoms': symptoms, 'evidence': json.dumps(chunks, ensure_ascii=False),
                          'detector_result': detected.model_dump_json() if detected else '',
                          'mode': 'both'}, headers=headers)
            response.raise_for_status()
            result = ModelResult.model_validate(response.json())
            if result.schema_version != '1.0':
                raise ValueError('Unsupported inference schema_version')
            if s.multimodal_enabled:
                # Both report features and boxes are bound to the ONE pre-retrieval detection.
                result.model_version, result.tongue_features = detected.model_version, detected.tongue_features
                result.fusion_result.update({k:v for k,v in detected.fusion_result.items() if k != 'qwen'})
                qwen = result.fusion_result.get('qwen', {})
                output = GeneratedOutput.model_validate(qwen.get('output', {}))
                ids = output.cited_chunk_ids
                if qwen.get('status') != 'valid' or not isinstance(ids, list) or any(i not in {c['chunk_id'] for c in chunks} for i in ids):
                    raise ValueError('Invalid Qwen output or evidence IDs')
                result.fusion_result['evidence_status'] = evidence_status
                result.fusion_result['evidence'] = [dict(c, entity_id=str(uuid5(NAMESPACE_URL, c['chunk_id'])),
                    title=c['source_title'], citation=(c['location'] if isinstance(c['location'], str)
                    else json.dumps(c['location'], ensure_ascii=False))) for c in chunks if c['chunk_id'] in ids]
                metrics['qwen_seconds'] = qwen.get('metrics', {}).get('seconds')
                result.fusion_result['stage_metrics'] = metrics
            return result
