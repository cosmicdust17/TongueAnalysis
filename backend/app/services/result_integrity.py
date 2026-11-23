"""YOLO owns visual findings; unverified generated visual claims never become facts."""
import re


def confirmed_features(annotations):
    grouped = {}
    for box in annotations['detections']:
        previous = grouped.get(box['class_name'])
        if not previous or box['score'] > previous['confidence']:
            grouped[box['class_name']] = {'name': box['name'], 'value': '检出'+box['name']+'特征', 'confidence': box['score']}
    features = list(grouped.values())
    if 'liewenshe' not in grouped:
        features.append({'name': '裂纹', 'value': '未检出裂纹特征', 'confidence': None})
    return features


def reconcile_analysis(generated, features):
    analysis = generated.get('analysis', '')
    safe, pending = [], list(generated.get('pending_observations', []))
    # Visual prose is kept for review, never used to overwrite the saved detector result.
    visual = re.compile(r'舌|苔|裂纹|齿痕|纹理|色泽|红色|紫色|白色|黄色|黑色|阴虚|阳虚|火旺|痰湿|证候|病因')
    for sentence in re.split(r'(?<=[。！？；])|\n', analysis):
        sentence = sentence.strip()
        if not sentence:
            continue
        if visual.search(sentence):
            pending.append(sentence)
        else:
            safe.append(sentence)
    facts = '、'.join(f['value'] for f in features)
    summary = '本次已保存的 YOLO 检测结果：'+facts+'。未检出不代表不存在。'
    if safe:
        summary += '\n症状与分析：'+''.join(safe)
    pending = list(dict.fromkeys(pending))[:10]
    if pending:
        summary += '\n待复核：Qwen 提出的额外舌象观察未经检测结果确认，详见待复核项。'
    return summary, pending
