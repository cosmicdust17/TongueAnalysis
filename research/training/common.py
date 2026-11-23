"""Shared paths and reproducibility helpers for image-only detection."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(r'E:\软件工程概论\DataSet\TWC-Tongue')
os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / 'results' / 'ultralytics_settings'))
os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'results' / 'matplotlib'))
Path(os.environ['YOLO_CONFIG_DIR']).mkdir(parents=True, exist_ok=True)
os.environ.setdefault('YOLO_OFFLINE', 'true')

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def classes(path):
    names = Path(path).read_text(encoding='utf-8-sig').splitlines()
    if len(names) != 21 or any(not n.strip() or n != n.strip() for n in names) or len(set(names)) != 21:
        raise ValueError('Expected exactly 21 unique, nonempty class names in original order')
    return names

def snapshot(folder, params):
    import torch
    import ultralytics
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'requirements-lock.txt').write_text(subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True), encoding='utf-8')
    env = dict(python=sys.version, executable=sys.executable, torch=torch.__version__,
               ultralytics=ultralytics.__version__, cuda_runtime=torch.version.cuda,
               cuda_available=torch.cuda.is_available(), parameters=params)
    if torch.cuda.is_available():
        env['gpu'] = torch.cuda.get_device_name(0)
        env['vram_bytes'] = torch.cuda.get_device_properties(0).total_memory
    write_json(folder / 'environment.json', env)

def require_cuda():
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable. CPU training is disabled; check environment and driver.')

def load_config(path):
    import yaml
    path = Path(path).resolve()
    config = yaml.safe_load(path.read_text(encoding='utf-8'))
    nc = config.get('nc')
    names = config.get('names', {})
    if not isinstance(nc, int) or nc < 1 or not isinstance(names, dict) or set(names) != set(range(nc)) or len(set(names.values())) != nc:
        raise ValueError('Expected contiguous unique class names matching nc')
    provenance = json.loads(path.with_suffix('.provenance.json').read_text(encoding='utf-8'))
    if provenance['config_sha256'] != digest(path):
        raise ValueError('Configuration changed after preparation')
    if 'nc' in provenance and (provenance['nc'] != nc or {int(k):v for k,v in provenance['names'].items()} != names):
        raise ValueError('Configuration class map differs from audited provenance')
    if 'audit' in provenance and digest(provenance['audit']) != provenance['audit_sha256']:
        raise ValueError('Re-audit report changed after configuration was approved')
    if 'clean_manifest' in provenance:
        manifest_path = Path(provenance['clean_manifest'])
        if digest(manifest_path) != provenance['clean_manifest_sha256']:
            raise ValueError('Clean manifest changed after re-audit')
        clean_rows = json.loads(manifest_path.read_text(encoding='utf-8'))
        expected_images = {str(Path(r['destination']).resolve()) for r in clean_rows if r['status'] == 'retained'}
        observed_images = {str(p.resolve()) for s in ('train', 'val', 'test') for p in (Path(config['path'])/s/'images').rglob('*')
                           if p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}}
        if observed_images != expected_images:
            raise ValueError('Clean image membership changed after re-audit')
        for row in clean_rows:
            if row['status'] == 'retained' and (digest(row['destination']) != row['image_sha256'] or digest(row['destination_label']) != row['destination_label_sha256']):
                raise ValueError('Clean image or label changed after re-audit')
    return config, provenance
