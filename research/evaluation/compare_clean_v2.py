"""Compare two frozen seven-class checkpoints on the same clean_v2 validation labels."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'training'))
from common import ROOT, digest, load_config, require_cuda, snapshot, write_json
from ultralytics import YOLO
from ultralytics.models.yolo.detect.val import DetectionValidator
from ultralytics.utils import ops
from ultralytics.utils.metrics import box_iou, smooth

FISSURE_ID = 2
CONFIDENCE = 0.218
MATCH_IOU = 0.5


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def table(path, rows):
    with Path(path).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(k for row in rows for k in row)))
        writer.writeheader()
        writer.writerows(rows)


def greedy_pairs(iou, threshold=MATCH_IOU):
    """Same non-SciPy one-to-one IoU matching as the installed Ultralytics validator."""
    pairs = np.array(np.nonzero(iou >= threshold)).T
    if len(pairs) > 1:
        pairs = pairs[iou[pairs[:, 0], pairs[:, 1]].argsort()[::-1]]
        pairs = pairs[np.unique(pairs[:, 1], return_index=True)[1]]
        pairs = pairs[np.unique(pairs[:, 0], return_index=True)[1]]
    return pairs


class EvidenceValidator(DetectionValidator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def update_metrics(self, preds, batch):
        for si, pred in enumerate(preds):
            prepared = self._prepare_batch(si, batch)
            target_mask = prepared['cls'] == FISSURE_ID
            gt = prepared['bboxes'][target_mask]
            fissure_mask = pred['cls'] == FISSURE_ID
            fissure_boxes = pred['bboxes'][fissure_mask]
            scores = pred['conf'][fissure_mask]
            selected = torch.where(scores >= CONFIDENCE)[0]
            fixed_boxes = fissure_boxes[selected]
            ious = box_iou(gt, fixed_boxes).cpu().numpy()
            pairs = greedy_pairs(ious)
            official = self._process_batch(
                dict(bboxes=fixed_boxes, cls=torch.full_like(scores[selected], FISSURE_ID)),
                dict(bboxes=gt, cls=prepared['cls'][target_mask]))['tp'][:, 0]
            assert set(np.flatnonzero(official)) == set(pairs[:, 1].tolist())
            original_gt = ops.scale_boxes(prepared['imgsz'], gt.clone(), prepared['ori_shape'], ratio_pad=prepared['ratio_pad'])
            original_pred = ops.scale_boxes(prepared['imgsz'], fissure_boxes.clone(), prepared['ori_shape'], ratio_pad=prepared['ratio_pad'])
            prediction_rows = [dict(index=i, xyxy=box, score=float(score),
                                    selected_at_fixed_conf=bool(score >= CONFIDENCE))
                               for i, (box, score) in enumerate(zip(original_pred.cpu().tolist(), scores.cpu().tolist()))]
            matched_gt = set(pairs[:, 0].tolist())
            matched_predictions = {int(selected[int(j)]) for j in pairs[:, 1]}
            false_predictions = [int(i) for i in selected.tolist() if int(i) not in matched_predictions]
            missed_gt = [i for i in range(len(gt)) if i not in matched_gt]
            all_ious = box_iou(gt, fissure_boxes).cpu().numpy()
            missed_reasons = []
            for i in missed_gt:
                possible = np.flatnonzero(all_ious[i] >= MATCH_IOU)
                max_score = float(scores[possible].max()) if len(possible) else None
                if max_score is not None and max_score < CONFIDENCE:
                    reason = 'matching_fissure_prediction_below_fixed_confidence'
                elif len(possible):
                    reason = 'one_to_one_matching_competition'
                elif len(fissure_boxes) and float(all_ious[i].max()) >= 0.1:
                    reason = 'fissure_prediction_localization_below_iou_0_5'
                else:
                    reason = 'no_matching_fissure_prediction_at_scan_conf_0_001'
                missed_reasons.append(dict(gt_index=i, reason=reason, max_matching_score=max_score))
            self.records.append(dict(image=str(Path(prepared['im_file']).resolve()),
                ground_truth=original_gt.cpu().tolist(), predictions=prediction_rows,
                matches=[dict(gt_index=int(i), prediction_index=int(selected[int(j)]), iou=float(ious[i,j])) for i,j in pairs],
                fp_prediction_indices=false_predictions, fn_gt_indices=missed_gt, fn_reasons=missed_reasons,
                tp=len(pairs), fp=len(false_predictions), fn=len(missed_gt)))
        super().update_metrics(preds, batch)


def evaluate(weights, tag, config, output, val_manifest):
    directory = output/tag
    if (directory/'metrics.json').exists():
        data = read(directory/'metrics.json')
        if data['weights_sha256'] != digest(weights) or data['validation_manifest_sha256'] != digest(output/'validation_manifest.json'):
            raise ValueError('Saved evaluation inputs differ; choose a fresh comparison output')
        return data, read(directory/'fissure_errors.json')
    model = YOLO(str(weights))
    if model.names != config['names']:
        raise ValueError('Checkpoint class mapping differs from clean_v2')
    holders = []
    def factory(**kwargs):
        validator = EvidenceValidator(**kwargs)
        holders.append(validator)
        return validator
    params = dict(data=str(ROOT/'datasets'/'clean_v2'/'data.yaml'), split='val', imgsz=640, batch=4,
        workers=0, device=0, half=False, conf=0.001, iou=0.7, max_det=300, rect=True,
        augment=False, agnostic_nms=False, single_cls=False, classes=None,
        plots=True, save_json=False, save_txt=False, project=str(output), name=tag, exist_ok=True)
    snapshot(directory, dict(params, weights=str(weights), fixed_confidence=CONFIDENCE, matching_iou=MATCH_IOU))
    metrics = model.val(validator=factory, **params)
    records = holders[0].records
    expected = {r['image'] for r in val_manifest}
    if {r['image'] for r in records} != expected or len(records) != len(expected):
        raise ValueError('Validation image membership mismatch')
    expected_gt = {r['image']:r['fissure_boxes'] for r in val_manifest}
    if any(len(r['ground_truth']) != expected_gt[r['image']] for r in records):
        raise ValueError('Validator changed the expected number of fissure annotations')
    per_class = []
    indices = list(metrics.box.ap_class_index)
    for cid, name in config['names'].items():
        if cid not in indices:
            raise ValueError('Expected class absent from validation metric results')
        p, r, ap50, ap = map(float, metrics.box.class_result(indices.index(cid)))
        per_class.append(dict(class_id=cid, name=name, precision=p, recall=r, ap50=ap50, ap50_95=ap))
    operating_index = int(smooth(metrics.box.f1_curve.mean(0), 0.1).argmax())
    total = {key:sum(r[key] for r in records) for key in ('tp','fp','fn')}
    total.update(precision=total['tp']/(total['tp']+total['fp']) if total['tp']+total['fp'] else 0.0,
        recall=total['tp']/(total['tp']+total['fn']) if total['tp']+total['fn'] else 0.0,
        confidence=CONFIDENCE, matching_iou=MATCH_IOU)
    fissure = next(r for r in per_class if r['class_id']==FISSURE_ID)
    result = dict(model=tag, weights=str(weights.resolve()), weights_sha256=digest(weights),
        validation_manifest_sha256=digest(output/'validation_manifest.json'),
        validation_images=len(records), fissure_gt_boxes=total['tp']+total['fn'],
        precision=fissure['precision'], recall=fissure['recall'], ap50=fissure['ap50'],
        ap50_95=fissure['ap50_95'], official_pr_confidence=float(metrics.box.px[operating_index]),
        official_pr_definition='Class-specific P/R at the checkpoint own smoothed mean-F1 optimum across all 7 classes; IoU 0.5.',
        fixed_confidence=total, per_class=per_class, parameters=params)
    write_json(directory/'fissure_errors.json', records)
    write_json(directory/'metrics.json', result)
    return result, records


def draw_panel(image, gt, predictions, record, title):
    page = Image.new('RGB', (700, 780), 'white')
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 18)
    scale = min(680/image.width, 600/image.height)
    tile = image.resize((round(image.width*scale), round(image.height*scale)), Image.Resampling.LANCZOS)
    x0 = (700-tile.width)//2
    page.paste(tile, (x0, 55))
    draw = ImageDraw.Draw(page)
    draw.text((12, 12), title, font=font, fill='black')
    def box(coords, color, text, bottom=False):
        a,b,c,d = coords
        corners = [x0+a*scale, 55+b*scale, x0+c*scale, 55+d*scale]
        draw.rectangle(corners, outline=color, width=3)
        label_y = min(655, corners[3]+2) if bottom else max(55, corners[1]-21)
        draw.text((corners[0], label_y), text, font=font, fill=color, stroke_width=1, stroke_fill='black')
    for i, coords in enumerate(gt):
        missed = record is not None and i in record['fn_gt_indices']
        box(coords, 'orange' if missed else 'lime', f'G{i}', bottom=True)
    if record:
        false = set(record['fp_prediction_indices'])
        for p in predictions:
            if p['selected_at_fixed_conf']:
                box(p['xyxy'], 'red' if p['index'] in false else 'cyan', f"P{p['index']}")
        gt_status = ', '.join(f"G{i}={'FN' if i in record['fn_gt_indices'] else 'matched'}" for i in range(len(gt))) or 'none'
        draw.text((12, 687), 'GT: '+gt_status, font=font, fill='black')
        for line, p in enumerate([p for p in predictions if p['selected_at_fixed_conf']]):
            status = 'FP' if p['index'] in false else 'TP'
            draw.text((12+(line%2)*340, 714+(line//2)*24), f"P{p['index']} {status}, score={p['score']:.3f}",
                      font=font, fill='red' if status=='FP' else 'teal')
    else:
        draw.text((12, 687), 'Green: annotated fissure boxes (ID 2)', font=font, fill='black')
    return page


def export_examples(old_records, new_records, output, reviewed):
    old = {r['image']:r for r in old_records}
    new = {r['image']:r for r in new_records}
    groups = {
        'old_fp_reduced':lambda a,b:a['fp']>b['fp'],
        'new_fp':lambda a,b:b['fp']>0,
        'old_fn_reduced':lambda a,b:a['fn']>b['fn'],
        'new_fn':lambda a,b:b['fn']>0,
        'common_fp':lambda a,b:a['fp']>0 and b['fp']>0,
        'common_fn':lambda a,b:a['fn']>0 and b['fn']>0,
    }
    examples = []
    used = set()
    for category, condition in groups.items():
        candidates = [path for path in old if condition(old[path],new[path])]
        is_fp = 'fp' in category
        def priority(path):
            a,b = old[path],new[path]
            error = 'fp' if is_fp else 'fn'
            reduction = a[error]-b[error] if 'reduced' in category else b[error]
            confirmed_negative = reviewed.get(path,{}).get('human_presence')=='absent'
            false_scores = [p['score'] for r in (a,b) for p in r['predictions'] if p['index'] in r['fp_prediction_indices']]
            return (-int(confirmed_negative and is_fp),-reduction,-max(false_scores, default=0),path)
        selected = [path for path in sorted(candidates,key=priority) if path not in used][:2]
        for path in selected:
            used.add(path)
            a,b = old[path],new[path]
            folder = output/'examples'/f'{len(examples)+1:02d}_{category}'
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path,folder/Path(path).name)
            label = Path(path).parent.parent/'labels'/Path(path).with_suffix('.txt').name
            shutil.copyfile(label,folder/'clean_v2_label.txt')
            with Image.open(path) as source:
                image = source.convert('RGB')
            pages = [draw_panel(image,a['ground_truth'],[],None,'clean_v2 GT fissure boxes (green)'),
                draw_panel(image,a['ground_truth'],a['predictions'],a,f"OLD @0.218: TP={a['tp']} FP={a['fp']} FN={a['fn']}"),
                draw_panel(image,b['ground_truth'],b['predictions'],b,f"NEW @0.218: TP={b['tp']} FP={b['fp']} FN={b['fn']}")]
            board = Image.new('RGB',(2100,780),'white')
            for i,page in enumerate(pages):
                board.paste(page,(i*700,0))
            board.save(folder/'comparison.jpg',quality=95)
            evidence = dict(category=category,image=path,old=a,new=b,user_review=reviewed.get(path),
                interpretation='FP/FN relative to clean_v2 validation labels at conf>=0.218 and IoU>=0.5; not a new human adjudication.',
                selection='Deterministic extreme-error examples, prioritize previously user-confirmed negative images for FP; not a random representative sample.')
            write_json(folder/'evidence.json',evidence)
            examples.append(dict(category=category,image=path,comparison=(folder/'comparison.jpg').relative_to(output).as_posix(),
                old_tp=a['tp'],old_fp=a['fp'],old_fn=a['fn'],new_tp=b['tp'],new_fp=b['fp'],new_fn=b['fn']))
    write_json(output/'examples.json',examples)
    return examples


def main(a):
    require_cuda()
    output = a.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    config, provenance = load_config(ROOT/'datasets'/'clean_v2'/'data.yaml')
    if config['nc']!=7 or config['names'][FISSURE_ID]!='liewenshe':
        raise ValueError('Expected seven-class clean_v2 mapping')
    from audit_data import parse_label
    val_manifest = []
    for row in read(Path(provenance['clean_manifest'])):
        if row['original_split']=='val':
            label=Path(row['destination_label'])
            boxes,errors=parse_label(label.read_text(encoding='utf-8-sig'),7)
            if errors:
                raise ValueError('Invalid validation label')
            val_manifest.append(dict(image=str(Path(row['destination']).resolve()), image_sha256=row['image_sha256'],
                label=str(label),label_sha256=digest(label),fissure_boxes=sum(b[0]==FISSURE_ID for b in boxes)))
    assert len(val_manifest)==244 and sum(r['fissure_boxes'] for r in val_manifest)==83
    write_json(output/'validation_manifest.json',val_manifest)
    old_weights = output/'model_snapshots'/'clean_v1_best.pt'
    new_weights = output/'model_snapshots'/'clean_v2_best.pt'
    if not old_weights.is_file():
        raise FileNotFoundError('Frozen clean_v1 checkpoint missing')
    if not new_weights.exists():
        shutil.copyfile(a.new_weights,new_weights)
    elif digest(a.new_weights)!=digest(new_weights):
        raise ValueError('New checkpoint changed since comparison snapshot')
    results, records = [], []
    for weights, tag in ((old_weights,'old_clean_v1'),(new_weights,'new_clean_v2')):
        metric,evidence=evaluate(weights,tag,config,output,val_manifest)
        results.append(metric)
        records.append(evidence)
    compared = [dict(model=r['model'],precision=r['precision'],recall=r['recall'],ap50=r['ap50'],
        recall_at_conf_0_218=r['fixed_confidence']['recall'],precision_at_conf_0_218=r['fixed_confidence']['precision'],
        tp_at_conf_0_218=r['fixed_confidence']['tp'],fp_at_conf_0_218=r['fixed_confidence']['fp'],
        fn_at_conf_0_218=r['fixed_confidence']['fn'],official_pr_confidence=r['official_pr_confidence']) for r in results]
    table(output/'comparison.csv',compared)
    write_json(output/'comparison.json',dict(models=results,split='clean_v2/val',test_evaluated=False,
        validation_images=244,fissure_boxes=83,matching_iou=MATCH_IOU,fixed_confidence=CONFIDENCE))
    review_rows=read(ROOT/'results'/'fissure_review'/'candidates.json')['candidates']
    reviewed={str((ROOT/'datasets'/'clean_v2'/'val'/'images'/Path(r['clean_image']).name).resolve()):r
              for r in review_rows if r['split']=='val'}
    examples=export_examples(*records,output,reviewed)
    lines=['# clean_v1 与 clean_v2 裂纹模型验证对比','',
        '旧、新best.pt均使用clean_v2同一份244张验证图、83个裂纹GT框；原始ID 7 / clean ID 2（liewenshe），共7类。未评估测试集。','',
        '| 模型 | 裂纹Precision | 裂纹Recall | 裂纹AP50 | Recall @ conf=0.218 |',
        '|---|---:|---:|---:|---:|']
    lines += [f"| {r['model']} | {r['precision']:.2%} | {r['recall']:.2%} | {r['ap50']:.2%} | {r['recall_at_conf_0_218']:.2%} |" for r in compared]
    delta={k:compared[1][k]-compared[0][k] for k in ('precision','recall','ap50','recall_at_conf_0_218')}
    lines += [f"| 新−旧（百分点） | {100*delta['precision']:+.2f} | {100*delta['recall']:+.2f} | {100*delta['ap50']:+.2f} | {100*delta['recall_at_conf_0_218']:+.2f} |",'',
        'Precision/Recall来自Ultralytics标准验证：各模型在7类平均F1平滑曲线最佳点的裂纹指标；阈值可不同，具体数值见comparison.csv。AP50以conf=0.001扫描、IoU=0.5计算。',
        '固定阈值项使用同一次验证的原始NMS结果，筛选score>=0.218后重新一对一匹配；TP/(TP+FN)，IoU>=0.5。避免低分框抢占匹配，也不以曲线插值代替计数。NMS IoU=0.7、max_det=300、FP32、imgsz640、batch4、rect=True，两模型一致。',
        'Ultralytics自带val_batch预测图和混淆矩阵采用默认绘图阈值0.25；本次0.218的判断以固定阈值计数及examples中的对照图为准。','',
        '| 模型 @0.218 | TP | FP | FN | Precision | Recall |','|---|---:|---:|---:|---:|---:|']
    lines += [f"| {r['model']} | {r['tp_at_conf_0_218']} | {r['fp_at_conf_0_218']} | {r['fn_at_conf_0_218']} | {r['precision_at_conf_0_218']:.2%} | {r['recall_at_conf_0_218']:.2%} |" for r in compared]
    lines += ['','## 典型误报、漏检对照图','',
        '左为clean_v2裂纹GT，中为旧模型，右为新模型。绿色GT，橙色未匹配GT（FN），青色匹配预测（TP），红色未匹配预测（FP）；全部模型框采用conf>=0.218。',
        '这里的误报/漏检均相对于当前验证标注。除已有人工结论外，未重新把图像判定为真实有/无裂纹；残余漏标可能影响指标。样例按错误类型确定性选取，属于典型失败案例，不能代替整体指标。','']
    lines += [f"- {r['category']}：[原图及旧新框对照]({r['comparison']})，{Path(r['image']).name}；旧 TP/FP/FN={r['old_tp']}/{r['old_fp']}/{r['old_fn']}，新={r['new_tp']}/{r['new_fp']}/{r['new_fn']}。" for r in examples]
    lines += ['','## 解释范围','',
        'clean_v2只追加已人工通过的28个裂纹框，其他类与划分保留。两模型在同一套修订验证标签上比较，不能与旧clean_v1历史验证数值直接拼接。',
        '部分补标验证图源于旧模型低阈值筛选及人工复核，该样本选择方式与验证集修订可能影响对比；单次seed42结果不代表跨随机种子或临床泛化结论。训练依然使用验证集早停，测试集留作最终评估。',
        '两份权重及哈希、完整每类指标、逐图FP/FN证据和曲线均已保存。没有增加类别，也没有修改验证标签以迎合预测。','']
    (output/'README.md').write_text('\n'.join(lines),encoding='utf-8')
    shutil.copyfile(Path(__file__),output/'compare_clean_v2_snapshot.py')
    for row in val_manifest:
        if digest(row['image'])!=row['image_sha256'] or digest(row['label'])!=row['label_sha256']:
            raise ValueError('Validation input changed during comparison')
    print('Comparison completed. Saved metrics table and typical FP/FN evidence; test set not evaluated.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--new-weights',type=Path,default=ROOT/'results'/'formal'/'clean-v2-yolo11n-seed42'/'weights'/'best.pt')
    parser.add_argument('--output',type=Path,default=ROOT/'results'/'comparison'/'clean-v1-vs-clean-v2')
    main(parser.parse_args())
