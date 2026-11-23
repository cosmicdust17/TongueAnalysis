"""Bounded, resumable official download for connections that stall on a single 4GB GET."""
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import requests

REVISION = '89644892e4d85e24eaac8bacfd4f463576704203'
SHA256 = '7de1838c87a5349b016c26a1c3f7d2bc400a3d485f95ef39a7059ffd734977a0'
URL = f'https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct/resolve/{REVISION}/model.safetensors'

def download():
    root = Path(os.environ['HF_HOME'])/'hub/models--Qwen--Qwen3-VL-2B-Instruct'
    target = root/'snapshots'/REVISION/'model.safetensors'
    if target.exists():
        with target.open('rb') as f:
            if hashlib.file_digest(f, 'sha256').hexdigest() != SHA256:
                raise ValueError('Cached official weight SHA256 mismatch')
        print(f'Cached official weight verified: {SHA256}', flush=True)
        return
    response = requests.get(URL, headers={'Range': 'bytes=0-0'}, timeout=(15, 60))
    response.raise_for_status()
    total = int(response.headers['Content-Range'].split('/')[-1])
    parts = root/'range-parts'
    parts.mkdir(parents=True, exist_ok=True)
    block = 32*1024*1024
    count = (total+block-1)//block
    def fetch(i):
        start, end = i*block, min(total, (i+1)*block)-1
        path = parts/f'{i:04d}.part'
        if path.exists() and path.stat().st_size == end-start+1:
            return path
        for attempt in range(3):
            try:
                r = requests.get(URL, headers={'Range': f'bytes={start}-{end}'}, stream=True, timeout=(15, 60))
                r.raise_for_status()
                if r.status_code != 206 or r.headers.get('Content-Range') != f'bytes {start}-{end}/{total}':
                    raise ValueError('Server did not honor byte range')
                with path.open('wb') as f:
                    for chunk in r.iter_content(1024*1024):
                        f.write(chunk)
                r.close()
                if path.stat().st_size != end-start+1:
                    raise ValueError('Incomplete range')
                print(f'part {i+1}/{count}', flush=True)
                return path
            except (requests.RequestException, ValueError):
                if attempt == 2:
                    raise
    with ThreadPoolExecutor(max_workers=4) as pool:
        paths = list(pool.map(fetch, range(count)))
    digest = hashlib.sha256()
    temporary = parts/'assembled.safetensors'
    with temporary.open('wb') as f:
        for path in paths:
            with path.open('rb') as piece:
                while chunk := piece.read(8*1024*1024):
                    digest.update(chunk)
                    f.write(chunk)
    if digest.hexdigest() != SHA256:
        raise ValueError('Official weight SHA256 mismatch')
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary.replace(target)
    print(f'Verified official SHA256 {SHA256}, bytes={total}', flush=True)

if __name__ == '__main__':
    download()
