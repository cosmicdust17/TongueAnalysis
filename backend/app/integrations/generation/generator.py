from app.core.config import settings
from app.services.result_integrity import confirmed_features


def build_report(result, symptoms, duration, evidence, annotations=None):
    """Deterministic evidence-constrained report; replace behind this boundary later."""
    enabled = settings().knowledge_retrieval_enabled
    if not enabled:
        evidence = []
    demo = result.is_demo or any(e.get('is_demo') for e in evidence)
    observations = '、'.join(f.value for f in result.tongue_features) or '模型未返回可展示的舌象特征'
    if result.is_demo:
        summary = '当前使用固定模拟结果，仅用于演示系统流程，不能据此判断身体状况。'
    elif evidence:
        summary = f'模型返回的舌象观察为：{observations}。已检索到 {len(evidence)} 条相关知识依据，请结合症状与原始来源查看。当前版本不据此作证候或疾病诊断。'
    else:
        summary = f'模型返回的舌象观察为：{observations}。知识图谱中未检索到足够依据，暂不形成进一步判断。'
    if not enabled:
        summary += '知识检索尚未启用。'
    qwen = result.fusion_result.get('qwen', {})
    generated = qwen.get('output', {}) if qwen.get('status') == 'valid' else {}
    features = [f.model_dump() for f in result.tongue_features]
    pending = []
    if annotations and annotations.get('available') and result.fusion_result.get('detector') == 'YOLO11n':
        features = confirmed_features(annotations)
        summary = generated.get('analysis') or summary
    else:
        summary = generated.get('analysis', summary)
    return {'schema_version': '1.0', 'model_version': result.model_version,
        'is_demo': demo, 'tongue_features': features,
        'symptoms_summary': generated.get('symptoms_summary', symptoms), 'duration': duration,
        'summary': summary, 'pending_observations': [], 'visual_source': 'saved_yolo',
        'yolo_detections': result.fusion_result.get('detections', []),
        'inference_metrics': {**qwen.get('metrics', {}), **result.fusion_result.get('stage_metrics', {})},
        'cited_chunk_ids': generated.get('cited_chunk_ids', []),
        'advice': '保持规律作息、均衡饮食，记录身体感受；如有持续不适，请咨询专业医生。',
        'evidence_count': len(evidence), 'evidence_status': result.fusion_result.get('evidence_status', ('available' if evidence else 'insufficient') if enabled else 'disabled'),
        'notice': '模拟演示数据，不代表个人健康结论。' if demo else ('内部联调模型输出；未检出不代表不存在，检出分数不是医学概率。本报告不替代专业诊断。' if result.fusion_result.get('detector') == 'YOLO11n' else '本报告用于健康信息参考，不替代专业诊断。'),
        'generator_version': 'evidence-template-1.0'}
