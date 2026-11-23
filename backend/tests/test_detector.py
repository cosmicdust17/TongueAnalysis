import importlib.util
from pathlib import Path
from app.integrations.inference.schemas import ModelResult
from app.integrations.generation.generator import build_report


spec = importlib.util.spec_from_file_location('detector_format', Path(__file__).resolve().parents[2] / 'model-service/predictor.py')
detector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(detector)


def test_no_fissure_does_not_invent_detection():
    result = ModelResult.model_validate(detector.format_result([], 'test-detector', 'test-hash'))
    assert not result.is_demo
    assert result.tongue_features[0].value == '未检出裂纹特征'
    assert result.tongue_features[0].confidence is None
    assert not result.fusion_result['detections'] and not result.fusion_result['query_terms']
    report = build_report(result, '测试', '近一周', [])
    assert report['tongue_features'][0]['value'] == '未检出裂纹特征'
    assert '内部联调' in report['notice']


def test_fissure_detection_uses_real_score():
    raw = [{'class_id': 2, 'class_name': 'liewenshe', 'score': .3, 'box_xyxy': [1, 2, 3, 4]},
           {'class_id': 2, 'class_name': 'liewenshe', 'score': .7, 'box_xyxy': [2, 3, 4, 5]}]
    result = ModelResult.model_validate(detector.format_result(raw, 'test-detector', 'test-hash'))
    assert result.tongue_features[0].value == '检出裂纹特征'
    assert result.tongue_features[0].confidence == .7
    assert result.fusion_result['detections'] == raw
    assert result.fusion_result['imgsz'] == 640 and result.fusion_result['conf'] == .218
