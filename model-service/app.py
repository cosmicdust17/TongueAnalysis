import asyncio
import logging
import os
import secrets
import sys
import json
import hashlib
from time import perf_counter
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi import FastAPI, File, Form, UploadFile, Header, HTTPException, Depends
from predictor import Predictor
from schemas import ModelResult
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
config = {**dotenv_values(root / '.env'), **dotenv_values(root.parent / '.env')}
os.environ.setdefault('MODEL_API_KEY', config.get('MODEL_API_KEY') or '')
for key in ('MODEL_WEIGHTS', 'MODEL_DATA_YAML', 'QWEN_MAX_NEW_TOKENS', 'QWEN_MAX_INPUT_TOKENS', 'QWEN_OFFLINE'):
    if config.get(key):
        os.environ.setdefault(key, config[key])

predictor = Predictor()
ready = False
engine = None
multimodal = os.getenv('MODEL_MODE', 'yolo') == 'qwen'
sys.path.insert(0, str(root / 'research/multimodal'))

def auth(authorization: str = Header(default='')):
    key = os.getenv('MODEL_API_KEY', '')
    if key and not secrets.compare_digest(authorization, 'Bearer ' + key):
        raise HTTPException(401, 'Invalid inference service credential')

@asynccontextmanager
async def lifespan(app):
    global ready, engine
    try:
        await asyncio.to_thread(predictor.load)
        if multimodal:
            from runtime import Engine
            engine = await asyncio.to_thread(Engine, os.getenv('QWEN_ADAPTER') or None)
        ready = True
    except Exception:
        logging.exception('Model unavailable: health ready=false; inference returns 503')
    yield

app = FastAPI(title='Tongue model service (integration boundary)', lifespan=lifespan)

@app.get('/health', dependencies=[Depends(auth)])
def health():
    return {'ready': ready, 'schema_version': '1.0', 'model_version': predictor.version if ready else None,
            'imgsz': 640, 'conf': 0.218, 'mode': 'qwen' if multimodal else 'yolo',
            'weights': getattr(predictor, 'weights_path', None),
            'qwen_model': os.getenv('QWEN_MODEL', 'Qwen/Qwen3-VL-2B-Instruct') if engine else None,
            'qwen_load_seconds': getattr(engine, 'load_seconds', None),
            'max_new_tokens': os.getenv('QWEN_MAX_NEW_TOKENS', '384')}

@app.post('/v1/infer', response_model=ModelResult, dependencies=[Depends(auth)])
async def infer(image: UploadFile = File(...), symptoms: str = Form(default='', max_length=200),
                evidence: str = Form(default='[]', max_length=100000),
                mode: str = Form(default='both'), detector_result: str = Form(default='', max_length=300000)):
    if not ready:
        await image.close()
        raise HTTPException(503, 'Trained model has not been connected')
    try:
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'input.jpg'
            size = 0
            with path.open('wb') as file:
                while chunk := await image.read(64 * 1024):
                    size += len(chunk)
                    if size > 10 * 1024 * 1024:
                        raise HTTPException(413, 'Image too large')
                    file.write(chunk)
            if not size:
                raise HTTPException(400, 'Image is empty')
            if detector_result:
                raw = ModelResult.model_validate_json(detector_result).model_dump()
                if raw['fusion_result'].get('image_sha256') != hashlib.sha256(path.read_bytes()).hexdigest():
                    raise HTTPException(422, 'Detector image identity mismatch')
            else:
                raw = await asyncio.to_thread(predictor.analyze, str(path), symptoms)
            if multimodal:
                from contracts import Chunk
                try:
                    chunks = [Chunk.model_validate(c).model_dump() for c in json.loads(evidence)]
                    if len(chunks) > 10:
                        raise ValueError('Too many evidence chunks')
                    generated = await asyncio.to_thread(engine.infer, str(path), symptoms,
                        raw['fusion_result']['detections'], chunks, mode)
                except ValueError as exc:
                    raise HTTPException(422, str(exc)) from exc
                if generated['status'] != 'valid':
                    diagnostic = root / 'storage/qwen-last-rejected.json'
                    diagnostic.write_text(json.dumps(generated, ensure_ascii=False, indent=2), encoding='utf-8')
                    logging.error('Invalid Qwen JSON output rejected')
                    raise HTTPException(502, 'Qwen returned invalid JSON')
                raw['fusion_result']['qwen'] = generated
                raw['fusion_result']['qwen_model'] = os.getenv('QWEN_MODEL', 'Qwen/Qwen3-VL-2B-Instruct')
            return ModelResult.model_validate(raw)
    finally:
        await image.close()

@app.post('/v1/detect', response_model=ModelResult, dependencies=[Depends(auth)])
async def detect(image: UploadFile = File(...)):
    # Same upload safeguards; detection-only phase avoids generating before retrieval.
    if not ready:
        await image.close()
        raise HTTPException(503, 'Model unavailable')
    try:
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'input.jpg'
            size = 0
            with path.open('wb') as file:
                while chunk := await image.read(65536):
                    size += len(chunk)
                    if size > 10 * 1024 * 1024:
                        raise HTTPException(413, 'Image too large')
                    file.write(chunk)
            if not size:
                raise HTTPException(400, 'Image is empty')
            return await asyncio.to_thread(predictor.analyze, str(path), '')
    finally:
        await image.close()
