"""Seven-class YOLO11n detector behind the existing HTTP contract."""
import hashlib
import os
import json
from time import perf_counter
from pathlib import Path
from threading import Lock

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WEIGHTS = ROOT / 'research/results/formal/clean-v1-yolo11n-seed42/weights/best.pt'
LABELS = ['hongshe', 'zishe', 'liewenshe', 'chihenshe', 'baitaishe', 'huangtaishe', 'heitaishe']
FEATURES = json.loads((ROOT / 'shared/tongue_features.json').read_text(encoding='utf-8'))
TITLES = [FEATURES[label]['name'] for label in LABELS]


def format_result(detections, model_version, weight_sha256):
    features = []
    for cid, title in enumerate(TITLES):
        matches = [d['score'] for d in detections if d['class_name'] == LABELS[cid]]
        if matches:
            features.append({'name': title, 'value': f'检出{title}特征', 'confidence': max(matches)})
        elif cid == 2:
            features.append({'name': title, 'value': '未检出裂纹特征', 'confidence': None})
    return {'schema_version': '1.0', 'model_version': model_version, 'is_demo': False,
            'tongue_features': features,
            'fusion_result': {'detector': 'YOLO11n', 'imgsz': 640, 'conf': 0.218,
                             'weights_sha256': weight_sha256, 'detections': detections,
                             'query_terms': [TITLES[i] for i in range(7) if any(d['class_name'] == LABELS[i] for d in detections)],
                             'note': '内部联调；检出分数不是医学概率，未检出不代表不存在。症状不参与此图像检测模型推理。'}}


class Predictor:
    def __init__(self):
        self.lock = Lock()

    def load(self):
        path = Path(os.getenv('MODEL_WEIGHTS', str(DEFAULT_WEIGHTS))).resolve()
        if not path.is_file():
            raise FileNotFoundError('Model weights unavailable')
        from ultralytics import YOLO
        self.model = YOLO(str(path))
        self.weights_path = str(path)
        if len(self.model.names) != 7 or set(self.model.names.values()) != set(LABELS):
            raise ValueError('Expected the trained seven-class label mapping')
        import yaml
        yaml_path = os.getenv('MODEL_DATA_YAML')
        if yaml_path:
            names = yaml.safe_load(Path(yaml_path).read_text(encoding='utf-8'))['names']
            if isinstance(names, dict):
                names = [names[i] for i in range(len(names))]
            if names != [self.model.names[i] for i in range(7)]:
                raise ValueError('Weight and YAML class mappings differ')
        self.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        self.version = path.parents[1].name + '-' + self.sha256[:12]

    def analyze(self, image_path: str, symptoms: str) -> dict:
        started = perf_counter()
        with self.lock:
            result = self.model.predict(source=image_path, imgsz=640, conf=0.218,
                                        device=os.getenv('MODEL_DEVICE', 'cpu'), save=False, verbose=False)[0]
        height, width = result.orig_shape
        detections = [{'class_id': int(box.cls.item()), 'class_name': self.model.names[int(box.cls.item())],
                       'score': float(box.conf.item()), 'box_xyxy': box.xyxy[0].tolist(),
                       'box_xyxy_normalized': [float(v) / (width if i % 2 == 0 else height) for i, v in enumerate(box.xyxy[0].tolist())]}
                      for box in result.boxes]
        raw = format_result(detections, self.version, self.sha256)
        raw['fusion_result']['image_sha256'] = hashlib.sha256(Path(image_path).read_bytes()).hexdigest()
        raw['fusion_result']['yolo_seconds'] = perf_counter()-started
        return raw
