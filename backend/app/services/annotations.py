"""Freeze observational labels and image-relative boxes into each report."""
import json
import math
from pathlib import Path
from PIL import Image
from app.core.config import ROOT

FEATURES = json.loads((ROOT / 'shared/tongue_features.json').read_text(encoding='utf-8'))


def annotation_snapshot(result, image_path, model_version):
    fusion = result.get('fusion_result', {})
    available = 'detections' in fusion
    with Image.open(image_path) as image:
        width, height = image.size
    boxes = []
    for raw in fusion.get('detections', []):
        label = raw.get('class_name')
        if label not in FEATURES:
            raise ValueError('Unknown detection class mapping')
        xyxy = raw.get('box_xyxy_normalized')
        if xyxy is None:
            x1, y1, x2, y2 = raw['box_xyxy']
            xyxy = [x1 / width, y1 / height, x2 / width, y2 / height]
        if len(xyxy) != 4 or not all(math.isfinite(float(v)) for v in xyxy):
            raise ValueError('Invalid detection coordinates')
        x1, y1, x2, y2 = [max(0., min(1., float(v))) for v in xyxy]
        if x2 <= x1 or y2 <= y1:
            raise ValueError('Empty detection box')
        boxes.append({**FEATURES[label], 'class_name': label, 'class_id': raw['class_id'],
                      'score': raw['score'], 'xyxy': [x1, y1, x2, y2]})
    return {'available': available, 'coordinate_format': 'xyxy_normalized',
            'image_width': width, 'image_height': height, 'model_version': model_version,
            'weights_sha256': fusion.get('weights_sha256'), 'detections': boxes}
