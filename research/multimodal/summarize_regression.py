import json,statistics
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'research/multimodal/results/fissure-regression'
rows=json.loads((OUT/'yolo-comparison.json').read_text(encoding='utf-8'))
records={phase:{p.stem:json.loads(p.read_text(encoding='utf-8')) for p in (OUT/phase).glob('*.json') if p.stem!='latest-rejection'} for phase in ('before','after','neutral','current','tip')}
common=[k for k,r in records['before'].items() if r.get('task',{}).get('status')=='completed' and records['after'].get(k,{}).get('task',{}).get('status')=='completed']
timing={}
for phase in ('before','after','current'):
    cohort=[records[phase][k] for k in common]
    timing[phase]={key:statistics.mean(r['report']['content']['inference_metrics'][key] for r in cohort) for key in ('yolo_seconds','bge_seconds','qwen_seconds')}
    timing[phase]['end_to_end_seconds']=statistics.mean(r['end_to_end_seconds'] for r in cohort)
summary={'matched_successful_cases':common,'timings':timing,'pdf_checks':[]}
for phase in ('after','neutral','current','tip'):
    for case,r in records[phase].items():
        if r['task']['status'] != 'completed':
            continue
        text=''.join(p.extract_text() for p in PdfReader(OUT/phase/(case+'.pdf')).pages)
        compact=''.join(text.split())
        content=r['report']['content']
        visible_observation = content.get('presentation', {}).get('observation')
        if visible_observation is None:
            visible_observation = r['raw_result']['fusion_result']['qwen']['output']['analysis']
        assert ''.join(visible_observation.split()) in compact
        assert '待复核' not in text
        for chunk in r['evidence']['items']:
            assert ''.join(chunk['text'].split()) in compact
        boxes=r['report']['content']['annotations']['detections']
        detections=r['raw_result']['fusion_result']['detections']
        assert len(boxes)==len(detections)
        assert [b['class_name'] for b in boxes]==[b['class_name'] for b in detections]
        summary['pdf_checks'].append({'phase':phase,'case':case,'shared_observation_in_pdf':True,'box_count':len(boxes),'citations':len(r['evidence']['items'])})
approved_tips = []
for case in ('03_S1296', '05_S2867'):
    entry = next(r for r in rows if r['case'] == case)
    review = json.loads((ROOT/'research/results/fissure_review/manual_review/pending_boxes'/case/'suggestions.json').read_text(encoding='utf-8'))
    expected = next(box['xyxy_pixels'] for box in review['proposed_additions']
                    if '舌尖' in box.get('rationale', '') and box.get('applied_to_dataset'))
    def iou(box):
        x1, y1, x2, y2 = box
        a, b, c, d = expected
        overlap = max(0, min(x2, c)-max(x1, a))*max(0, min(y2, d)-max(y1, b))
        return overlap/((x2-x1)*(y2-y1)+(c-a)*(d-b)-overlap)
    approved_tips.append({'case':case,'reference_xyxy':expected,
        'max_iou':{v:max((iou(b['xyxy']) for b in data['boxes'] if b['class_name']=='liewenshe'),default=0)
                   for v,data in entry['models'].items()}})
summary['approved_tips']=approved_tips
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
lines=['# 人工审核图 YOLO 固定阈值回归','', 'conf=0.218；imgsz=640。28例均曾参与审核/标签修订；train图参与训练，val图参与开发验证，不能作独立测试成绩。正式test未读取。','', '|案例|人工参考|来源|v1裂纹框|v2裂纹框|','|---|---|---|---:|---:|']
for row in rows:
    count=lambda v:sum(b['class_name']=='liewenshe' for b in row['models'][v]['boxes'])
    lines.append(f"|{row['case']}|{'有' if row['human']=='present' else '无'}|{row['split']}|{count('v1')}|{count('v2')}|")
lines += ['', '完整中文标签由 shared/tongue_features.json 映射；逐框分数和像素坐标见 yolo-comparison.json。']
(OUT/'YOLO_TABLE.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
