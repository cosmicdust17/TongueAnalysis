"""Single image detection with original IDs, names and checkpoint identity."""
import argparse
from collections import defaultdict
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'training'))
from common import ROOT, digest, write_json

def predict(a):
    from ultralytics import YOLO
    model = YOLO(str(a.weights))
    if len(model.names) != 21: raise ValueError('Expected a fine-tuned 21-class checkpoint')
    if a.output.exists(): raise FileExistsError('Prediction output exists; choose a new --output')
    a.output.mkdir(parents=True)
    result = model.predict(source=str(a.image.resolve()), imgsz=640, conf=a.conf,
                           device=a.device, save=False, verbose=False)[0]
    detections, grouped = [], defaultdict(list)
    for box in result.boxes:
        cid = int(box.cls.item())
        detection = dict(class_id=cid, class_name=model.names[cid], model_score=float(box.conf.item()),
                         box_xyxy_pixels=box.xyxy[0].tolist())
        grouped[str(cid)].append(detection); detections.append(detection)
    write_json(a.output/'prediction.json', dict(schema_version='tongue-detection-1.0',
        model_version='yolo11n-sha256:'+digest(a.weights), image=str(a.image.resolve()),
        image_height=result.orig_shape[0], image_width=result.orig_shape[1],
        confidence_threshold=a.conf, detections=detections,
        by_class={cid:dict(class_id=int(cid), class_name=model.names[int(cid)], count=len(items),
            max_model_score=max(d['model_score'] for d in items), detections=items) for cid,items in grouped.items()},
        note='Model scores are not calibrated medical probabilities. No disease interpretation.'))
    result.save(filename=str(a.output/'prediction.jpg'))
    print(f'Prediction complete. Detections: {len(detections)}')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--weights', type=Path, required=True)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--output', type=Path, default=ROOT/'results'/'prediction')
    p.add_argument('--conf', type=float, default=0.25)
    p.add_argument('--device', default='0')
    a = p.parse_args()
    if not 0 <= a.conf <= 1: p.error('Confidence must be within [0,1]')
    predict(a)
