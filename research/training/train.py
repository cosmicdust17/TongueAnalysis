"""Fine-tune pretrained YOLO11n; never start a long CPU run."""
import argparse
from pathlib import Path
import shutil
from common import ROOT, digest, load_config, require_cuda, snapshot, write_json

def train(a):
    require_cuda()
    config, provenance = load_config(a.data)
    if bool(a.smoke) != bool(provenance['smoke']):
        raise ValueError('Smoke/formal configuration mismatch')
    if not a.smoke and not provenance['formal_allowed']:
        raise ValueError('Formal training blocked by audit')
    from ultralytics import YOLO
    import torch
    if a.weights.suffix != '.pt' or a.weights.name != 'yolo11n.pt':
        raise ValueError('Use the pretrained yolo11n.pt checkpoint for this baseline')
    output = ROOT/'results'/('smoke' if a.smoke else 'formal')/a.name
    if output.exists(): raise FileExistsError('Run exists; choose a new --name')
    params = dict(data=str(a.data.resolve()), epochs=1 if a.smoke else a.epochs,
                  patience=20, imgsz=640, batch=a.batch, workers=0, seed=42,
                  device=0, deterministic=True, pretrained=True, plots=True, save=True,
                  cache=False, amp=False, project=str(output.parent), name=output.name,
                  exist_ok=True, close_mosaic=0 if a.smoke else 10)
    snapshot(output, params)
    shutil.copyfile(a.data, output/'dataset.yaml')
    write_json(output/'class_mapping.json', config['names'])
    write_json(output/'data_provenance.json', provenance)
    # AMP is disabled to avoid implicit downloads of a different model for AMP checks.
    weights = a.weights.resolve()
    if not weights.exists():
        raise FileNotFoundError('Download official yolo11n.pt to research/weights first')
    write_json(output/'pretrained.json', dict(path=str(weights), sha256=digest(weights)))
    adjustments = []
    while True:
        try:
            model = YOLO(str(weights))
            model.train(**params)
            break
        except torch.cuda.OutOfMemoryError:
            if params['batch'] <= 1: raise
            old = params['batch']; params['batch'] = max(1, old//2)
            adjustments.append(dict(reason='CUDA out of memory; restart from pretrained', old_batch=old, new_batch=params['batch']))
            write_json(output/'batch_adjustments.json', adjustments)
            del model
            import gc
            gc.collect(); torch.cuda.empty_cache()
            print(f'CUDA OOM: restarting with batch={params["batch"]}', flush=True)
    write_json(output/'actual_parameters.json', params)
    write_json(output/'batch_adjustments.json', adjustments)
    for name in ('best.pt','last.pt'):
        if not (output/'weights'/name).is_file(): raise RuntimeError('Missing trained checkpoint: '+name)
    print('Training completed; checkpoints and actual configuration saved.')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', type=Path, default=ROOT/'configs'/'tongue21.yaml')
    p.add_argument('--weights', type=Path, default=ROOT/'weights'/'yolo11n.pt')
    p.add_argument('--smoke', action='store_true')
    p.add_argument('--epochs', type=int, default=100)
    p.add_argument('--batch', type=int, default=4)
    p.add_argument('--name', default='yolo11n-seed42')
    a = p.parse_args()
    if a.batch < 1 or a.epochs < 1 or Path(a.name).name != a.name: p.error('Invalid batch, epochs or run name')
    train(a)
