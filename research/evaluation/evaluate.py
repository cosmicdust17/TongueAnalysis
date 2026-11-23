"""Validation for tuning; test only for a frozen final model."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'training'))
from common import ROOT, digest, load_config, require_cuda, snapshot, write_json

def evaluate(a):
    require_cuda()
    config, provenance = load_config(a.data)
    if a.split == 'test' and (not a.final_test or provenance['smoke']):
        raise ValueError('Test requires --final-test and a formal dataset; freeze parameters first')
    from ultralytics import YOLO
    model = YOLO(str(a.weights))
    if list(model.names.values()) != list(config['names'].values()):
        raise ValueError('Checkpoint class mapping differs from data configuration')
    output = ROOT/'results'/'evaluation'/a.name
    if output.exists(): raise FileExistsError('Evaluation exists; choose a new --name')
    snapshot(output, vars(a)|{'weights':str(a.weights), 'data':str(a.data)})
    metrics = model.val(data=str(a.data.resolve()), split=a.split, imgsz=640, batch=4,
                        workers=0, device=0, plots=True, save_json=True,
                        project=str(output.parent), name=output.name, exist_ok=True)
    per_class = []
    indices = list(metrics.box.ap_class_index)
    for cid, name in config['names'].items():
        if cid in indices:
            i = indices.index(cid)
            p,r,ap50,ap = map(float,metrics.box.class_result(i))
            values = dict(precision=p, recall=r, mAP50=ap50, mAP50_95=ap)
        else: values = dict(precision=None, recall=None, mAP50=None, mAP50_95=None)
        per_class.append(dict(class_id=cid, name=name, **values))
    write_json(output/'metrics.json', dict(split=a.split, weights_sha256=digest(a.weights),
        precision=float(metrics.box.mp), recall=float(metrics.box.mr), mAP50=float(metrics.box.map50),
        mAP50_95=float(metrics.box.map), per_class=per_class,
        note='Absent classes have null metrics; smoke metrics are not model quality estimates.'))
    print('Evaluation complete. Metrics and plots saved.')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--weights', type=Path, required=True)
    p.add_argument('--data', type=Path, default=ROOT/'configs'/'tongue21.yaml')
    p.add_argument('--split', choices=['val','test'], default='val')
    p.add_argument('--final-test', action='store_true')
    p.add_argument('--name', default='validation')
    evaluate(p.parse_args())
