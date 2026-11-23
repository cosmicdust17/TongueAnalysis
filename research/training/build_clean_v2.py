"""Copy clean_v1 and append only user-approved fissure boxes; no training."""
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
import shutil

from PIL import Image
import yaml

from audit_data import IMAGE_EXTS, parse_label
from common import ROOT, digest, load_config, write_json

SOURCE = ROOT/'datasets'/'clean_v1'
TARGET = ROOT/'datasets'/'clean_v2'
LOGS = ROOT/'results'/'clean_v2'
REVIEW = ROOT/'results'/'fissure_review'
MANUAL = REVIEW/'manual_review'
DATE = '2026-11-19'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def table(path, rows, fields=None):
    with Path(path).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or list(dict.fromkeys(k for row in rows for k in row)))
        writer.writeheader()
        writer.writerows(rows)


def approved_line(box):
    if box['approval'] != 'approved_by_user' or box['original_class_id'] != 7 or box['clean_class_id'] != 2:
        raise ValueError('Unapproved box or unexpected class mapping')
    x1, y1, x2, y2 = box['xyxy_normalized']
    coords = box['yolo_normalized']
    wanted = [(x1+x2)/2, (y1+y2)/2, x2-x1, y2-y1]
    if not all(math.isfinite(v) for v in [x1, y1, x2, y2, *coords]):
        raise ValueError('Nonfinite approved coordinate')
    if not 0 <= x1 < x2 <= 1 or not 0 <= y1 < y2 <= 1 or max(abs(a-b) for a, b in zip(coords, wanted)) > 1e-12:
        raise ValueError('Inconsistent approved box coordinates')
    line = '2 ' + ' '.join(f'{v:.12f}' for v in coords) + '\n'
    parsed, errors = parse_label(line, 7)
    if errors or len(parsed) != 1:
        raise ValueError('Invalid approved YOLO row')
    return line


def prepare_plan():
    candidates = read(REVIEW/'candidates.json')['candidates']
    receipt = read(MANUAL/'box_review_v2.json')
    previous = {row['box_id']: row['xyxy_pixels'] for row in receipt['previous_boxes_approved']}
    approved_ids, plan = set(), []
    for row in candidates:
        number = int(row['candidate_id'][:2])
        if row['split'] not in ('train', 'val'):
            raise ValueError('Manual changes may only target train/val')
        evidence = read(REVIEW/row['evidence'])
        label = Path(evidence['clean_label']).resolve()
        image = Path(evidence['image']).resolve()
        if not label.is_relative_to(SOURCE) or not image.is_relative_to(SOURCE):
            raise ValueError('Review path outside clean_v1')
        if digest(label) != evidence['clean_label_sha256'] or digest(image) != evidence['image_sha256']:
            raise ValueError('Reviewed source has changed')
        if number in (16, 22, 28):
            boxes, errors = parse_label(label.read_text(encoding='utf-8-sig'), 7)
            if errors or any(b[0] == 2 for b in boxes) or row['human_presence'] != 'absent':
                raise ValueError('Confirmed absent image unexpectedly has fissure annotations')
            continue
        suggestion_path = REVIEW/row['suggestions']
        suggestion = read(suggestion_path)
        if suggestion['proposed_replacements']:
            raise ValueError('Replacement annotations are outside this approved change')
        additions = suggestion['proposed_additions']
        for box in additions:
            if box['box_id'] in previous:
                if box['approval'] != 'approved_by_user' or box['xyxy_pixels'] != previous[box['box_id']]:
                    raise ValueError('Previously approved box changed')
            elif number in (3, 5) and box['box_id'] == f"{row['candidate_id']}:addition:2":
                expected = receipt['added_tip_proposals'][str(number)]['xyxy']
                if box['xyxy_pixels'] != expected:
                    raise ValueError('Tip box changed since the figure approved by the user')
                box.update(approval='approved_by_user', approval_label='已通过', reviewer='User', review_date=DATE)
            else:
                raise ValueError('Unexpected box without an explicit approval record')
            if box['box_id'] in approved_ids:
                raise ValueError('Duplicate approved box ID')
            approved_ids.add(box['box_id'])
            approved_line(box)
        plan.append(dict(candidate_id=row['candidate_id'], candidate_number=number, split=row['split'],
            source_image=str(image), source_label=str(label),
            image_relative=image.relative_to(SOURCE).as_posix(), label_relative=label.relative_to(SOURCE).as_posix(),
            source_image_sha256=digest(image), source_label_sha256=digest(label),
            width=suggestion['width'], height=suggestion['height'],
            suggestions=str(suggestion_path), suggestions_sha256=digest(suggestion_path), additions=additions))
    if len(plan) != 25 or len(approved_ids) != 28 or not set(previous).issubset(approved_ids):
        raise ValueError('Expected 25 reviewed images and exactly 28 approved additions')
    return plan


def finalize_review(plan):
    backup = LOGS/'review_before_application'
    paths = [REVIEW/name for name in ('candidates.csv', 'candidates.json', 'summary.json', 'README.md')]
    paths += [MANUAL/name for name in ('review_checklist.csv', 'pending_box_checklist.csv', 'awaiting_tip_confirmation.csv',
                                     'review.json', 'summary.json', 'README.md')]
    paths += list((MANUAL/'decisions').glob('*.json'))
    paths += [Path(p['suggestions']) for p in plan]
    for path in paths:
        target = backup/path.relative_to(REVIEW)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    by_id = {p['candidate_id']: p for p in plan}
    data = read(REVIEW/'candidates.json')
    reviews = read(MANUAL/'review.json')['decisions']
    decisions = {r['candidate_id']: r for r in reviews}
    checklist = list(csv.DictReader((MANUAL/'pending_box_checklist.csv').open(encoding='utf-8-sig', newline='')))
    for row in data['candidates']:
        cid = row['candidate_id']
        decision = decisions[cid]
        if cid in by_id:
            item = by_id[cid]
            decision.update(box_approval='approved_by_user', box_approval_label='已通过',
                approved_box_count=len(item['additions']), pending_box_count=0,
                annotation_action='approved_additions_applied_to_clean_v2', dataset_labels_changed=True,
                applied_dataset_version='clean_v2', applied_label=str(TARGET/item['label_relative']),
                source_clean_v1_unchanged=True)
            decision['human_comment'] += ' 最新结论：全部建议框已通过，仅写入独立clean_v2；clean_v1不变。'
            suggestion = read(Path(item['suggestions']))
            suggestion['proposed_additions'] = item['additions']
            for box in suggestion['proposed_additions']:
                box.update(applied_to_dataset=True, applied_dataset_version='clean_v2', applied_label=decision['applied_label'])
            suggestion['decision'] = decision.copy()
            suggestion['application_note'] = 'All proposals approved; appended only to independent clean_v2. Earlier draft notes retained as history.'
            write_json(item['suggestions'], suggestion)
            write_json(MANUAL/'decisions'/f'{cid}.json', decision)
        for key in ('box_approval', 'box_approval_label', 'approved_box_count', 'pending_box_count', 'annotation_action', 'human_comment'):
            row[key] = decision[key]
        row['applied_dataset_version'] = 'clean_v2' if cid in by_id else ''
    for row in checklist:
        item = by_id[row['candidate_id']]
        row.update(action='approved_additions_applied_to_clean_v2', box_approval='approved_by_user', box_approval_label='已通过',
            approved_box_count=len(item['additions']), pending_box_count=0,
            approved_boxes=json.dumps([b['box_id'] for b in item['additions']]), pending_boxes='[]',
            applied_dataset_version='clean_v2', applied_label=str(TARGET/item['label_relative']))
    summary = read(MANUAL/'summary.json')
    summary.update(review_round=3, boxes_user_approved=28, pending_box_images=0, pending_box_numbers=[],
        pending_suggestion_boxes=0, fully_approved_positive_images=25, dataset_label_edits=True,
        applied_dataset_version='clean_v2', applied_label_images=25, applied_addition_boxes=28,
        clean_v1_unchanged=True, test_unchanged=True, training_started=False)
    data['human_review_summary'] = summary
    table(REVIEW/'candidates.csv', data['candidates'])
    write_json(REVIEW/'candidates.json', data)
    table(MANUAL/'review_checklist.csv', reviews)
    table(MANUAL/'pending_box_checklist.csv', checklist)
    table(MANUAL/'awaiting_tip_confirmation.csv', [], list(checklist[0]))
    write_json(MANUAL/'review.json', dict(summary=summary, decisions=reviews))
    write_json(MANUAL/'summary.json', summary)
    root_summary = read(REVIEW/'summary.json')
    root_summary['human_review'] = summary
    write_json(REVIEW/'summary.json', root_summary)
    write_json(MANUAL/'box_review_v3.json', dict(review_date=DATE, reviewer='User',
        approval='03 and 05 new tip boxes approved; all 28 suggested boxes approved',
        applied_dataset=str(TARGET), modified_images=25, added_boxes=28, pending_boxes=0, training_started=False))
    header = '# 全部裂纹框已通过并写入独立clean_v2\n\n28个建议新增框已全部通过，已写入clean_v2的25张train/val图片标签；原始数据、clean_v1、测试集及其他类别标注保留。尚未训练。\n\n[clean_v2验收报告](../../clean_v2/README.md) / [全部复核清单](review_checklist.csv) / [应用记录](box_review_v3.json)。\n\n以下为上一轮建议图和历史说明，图中文字“待确认”已由本轮批准记录取代。\n\n'
    (MANUAL/'README.md').write_text(header+(backup/'manual_review'/'README.md').read_text(encoding='utf-8'), encoding='utf-8')
    (REVIEW/'README.md').write_text('# 裂纹复核已全部通过\n\n28个新增裂纹框已通过，仅写入独立clean_v2，共修改25张图片标签。16、22、28号仍无裂纹；其他类别保留，未训练。\n\n[人工复核清单](candidates.csv) / [应用说明](manual_review/README.md) / [clean_v2验收报告](../clean_v2/README.md)。\n', encoding='utf-8')


def main():
    if TARGET.exists() or LOGS.exists():
        raise FileExistsError('clean_v2 or its logs already exist; refusing to overwrite a reviewed dataset')
    config, provenance = load_config(SOURCE/'data.yaml')
    if config['names'].get(2) != 'liewenshe':
        raise ValueError('Unexpected fissure class mapping')
    source_rows = [r for r in read(Path(provenance['clean_manifest'])) if r['status']=='retained']
    plan = prepare_plan()
    by_label = {p['label_relative']: p for p in plan}
    immutable = {str(SOURCE/name): digest(SOURCE/name) for name in ('data.yaml', 'data.provenance.json', 'class_mapping.json')}
    source_members = {str(Path(r['destination']).relative_to(SOURCE)) for r in source_rows}
    LOGS.mkdir(parents=True)
    TARGET.mkdir(parents=True)
    write_json(LOGS/'approved_additions.json', dict(review_date=DATE, reviewer='User',
        latest_approval='User approved the new tip boxes in 03 and 05 and requested application of all approved boxes',
        coordinate_policy='Approved normalized coordinates are authoritative; pixel bounds in review figures are outward-rounded display values.',
        source_config_sha256=digest(SOURCE/'data.yaml'), source_manifest_sha256=provenance['clean_manifest_sha256'], images=plan))
    manifest, changes, errors, legacy_pixel_differences = [], [], [], []
    stats = Counter()
    class_images, class_boxes = Counter(), Counter()
    byte_groups, pixel_groups = defaultdict(list), defaultdict(list)
    for index, row in enumerate(source_rows, 1):
        image, label = Path(row['destination']), Path(row['destination_label'])
        image_rel, label_rel = image.relative_to(SOURCE), label.relative_to(SOURCE)
        target_image, target_label = TARGET/image_rel, TARGET/label_rel
        target_image.parent.mkdir(parents=True, exist_ok=True)
        target_label.parent.mkdir(parents=True, exist_ok=True)
        if image.is_symlink() or label.is_symlink():
            raise ValueError('Expected physical source files')
        before = label.read_bytes()
        if digest(image) != row['image_sha256'] or digest(label) != row['destination_label_sha256']:
            raise ValueError('clean_v1 changed before copying')
        shutil.copyfile(image, target_image)
        shutil.copyfile(label, target_label)
        change = by_label.get(label_rel.as_posix())
        if change:
            appended = ''.join(approved_line(b) for b in change['additions']).encode('ascii')
            separator = b'' if not before or before.endswith((b'\n', b'\r')) else b'\n'
            target_label.write_bytes(before+separator+appended)
            changes.append(dict(candidate_id=change['candidate_id'], split=change['split'], source_label=str(label),
                destination_label=str(target_label), before_sha256=digest(label), after_sha256=digest(target_label),
                added_boxes=len(change['additions']), added_box_ids=[b['box_id'] for b in change['additions']]))
        boxes, parse_errors = parse_label(target_label.read_text(encoding='utf-8-sig'), 7)
        old_boxes, old_errors = parse_label(before.decode('utf-8-sig'), 7)
        if old_errors or parse_errors or not boxes:
            errors.append(dict(image=str(target_image), errors=parse_errors or old_errors or ['Empty label']))
        if boxes[:len(old_boxes)] != old_boxes or len(boxes)-len(old_boxes) != (len(change['additions']) if change else 0):
            raise ValueError('Original annotation rows were changed or extra rows were introduced')
        if [b for b in boxes if b[0]!=2] != [b for b in old_boxes if b[0]!=2]:
            raise ValueError('Other-class annotation changed')
        if change and any(b[0]!=2 for b in boxes[len(old_boxes):]):
            raise ValueError('Addition outside fissure class')
        if change and not target_label.read_bytes().startswith(before):
            raise ValueError('Source annotation bytes were not preserved')
        if not change and target_label.read_bytes()!=before:
            raise ValueError('Untouched label bytes changed')
        with Image.open(target_image) as im:
            im.load()
            if im.getexif().get(274, 1) != 1:
                raise ValueError('Unexpected EXIF orientation')
            rgb = im.convert('RGB')
            pixel_sha = hashlib.sha256(str(rgb.size).encode()+rgb.tobytes()).hexdigest()
            if change and rgb.size != (change['width'], change['height']):
                raise ValueError('Approved coordinates refer to different image dimensions')
        copied_sha = digest(target_image)
        if copied_sha != row['image_sha256']:
            raise ValueError('Image file content changed')
        # Compare both files with the same decoder; historical RGB hashes can depend on its version.
        with Image.open(image) as original_image:
            original_rgb = original_image.convert('RGB')
            if original_rgb.size != rgb.size or original_rgb.tobytes() != rgb.tobytes():
                raise ValueError('Source and copy decode to different pixels')
        if pixel_sha != row['source_pixel_sha256']:
            legacy_pixel_differences.append(dict(image_relative=image_rel.as_posix(),
                legacy_pixel_sha256=row['source_pixel_sha256'], current_pixel_sha256=pixel_sha,
                file_sha256_matches_legacy=True, current_source_and_copy_pixels_equal=True))
        byte_groups[copied_sha].append(image_rel.as_posix())
        pixel_groups[pixel_sha].append(image_rel.as_posix())
        split = image_rel.parts[0]
        stats[(split, 'images')] += 1
        stats[(split, 'boxes')] += len(boxes)
        stats[(split, 'added_boxes')] += len(boxes)-len(old_boxes)
        stats[(split, 'changed_images')] += bool(change)
        for cid in {b[0] for b in boxes}:
            class_images[(split, cid)] += 1
        for b in boxes:
            class_boxes[(split, b[0])] += 1
        manifest.append(dict(status='retained', original_relative=image_rel.as_posix(), original_split=split,
            source_image=str(image), source_label=str(label), source_label_sha256=digest(label),
            destination=str(target_image), destination_label=str(target_label),
            image_sha256=copied_sha, pixel_sha256=pixel_sha, destination_label_sha256=digest(target_label),
            added_boxes=len(boxes)-len(old_boxes)))
        if index%500==0:
            print(f'Copied and checked {index}/{len(source_rows)} images.', flush=True)
    for split in ('train', 'val', 'test'):
        images = {str(p.relative_to(TARGET)) for p in (TARGET/split/'images').rglob('*') if p.suffix.lower() in IMAGE_EXTS}
        expected = {p for p in source_members if Path(p).parts[0]==split}
        labels = {p.relative_to(TARGET/split/'labels') for p in (TARGET/split/'labels').rglob('*.txt')}
        wanted_labels = {Path(p).relative_to(split+'/images').with_suffix('.txt') for p in images}
        if images!=expected or labels!=wanted_labels:
            raise ValueError('Image/label pairing or split membership changed')
    duplicates = [dict(kind=kind, images=members) for kind, groups in [('file_sha256', byte_groups), ('pixel_sha256', pixel_groups)]
                  for members in groups.values() if len(members)>1]
    if duplicates:
        errors.append(dict(exact_duplicate_groups=duplicates))
    # Recheck every original image/label after copying; test bytes are compared, never used for model evaluation.
    for row in source_rows:
        if digest(row['destination'])!=row['image_sha256'] or digest(row['destination_label'])!=row['destination_label_sha256']:
            raise ValueError('clean_v1 changed during the build')
    if any(digest(path)!=value for path, value in immutable.items()):
        raise ValueError('clean_v1 metadata changed')
    if stats[('test', 'changed_images')] or len(changes)!=25 or sum(c['added_boxes'] for c in changes)!=28:
        raise ValueError('Unexpected change counts or modified test labels')
    counts = [dict(split=s, new_id=cid, original_id=next(int(k) for k, v in provenance['original_to_new'].items() if v==cid),
                   name=name, images=class_images[(s,cid)], boxes=class_boxes[(s,cid)])
              for s in ('train','val','test') for cid,name in config['names'].items()]
    summary = dict(dataset_version='tongue-clean-v2', parent='clean_v1', audit_passed=not errors,
        total_images=len(manifest), modified_images=len(changes), added_fissure_boxes=28,
        splits={s:{k:stats[(s,k)] for k in ('images','boxes','changed_images','added_boxes')} for s in ('train','val','test')},
        class_counts=counts, missing_labels=0, empty_labels=0, orphan_labels=0,
        label_format='class_id x_center y_center width height; normalized YOLO detection',
        label_format_errors=errors, cross_split_exact_duplicates=0 if not duplicates else 'see errors',
        clean_v1_hashes_unchanged=True, all_image_bytes_unchanged=True, other_class_rows_unchanged=True,
        existing_fissure_rows_unchanged=True, test_images_and_labels_byte_identical=True,
        legacy_pixel_digest_differences=len(legacy_pixel_differences),
        pixel_verification='Current source/copy RGB dimensions and bytes compared directly; file SHA-256 checked against clean_v1 manifest',
        inherited_limits=read(ROOT/'results'/'clean_v1'/'reaudit.json')['limitation'],
        patient_independence='unknown; inherited from clean_v1', training_started=False, formal_allowed=not errors)
    write_json(LOGS/'clean_manifest.json', manifest)
    write_json(LOGS/'reaudit.json', summary)
    write_json(LOGS/'changes.json', changes)
    write_json(LOGS/'legacy_pixel_hash_differences.json', legacy_pixel_differences)
    table(LOGS/'changes.csv', changes)
    table(LOGS/'class_counts.csv', counts)
    shutil.copyfile(SOURCE/'class_mapping.json', TARGET/'class_mapping.json')
    config['path'] = TARGET.as_posix()
    (TARGET/'data.yaml').write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding='utf-8')
    new_provenance = dict(provenance, config_sha256=digest(TARGET/'data.yaml'), dataset_version='tongue-clean-v2',
        parent_dataset=str(SOURCE), audit=str(LOGS/'reaudit.json'), audit_sha256=digest(LOGS/'reaudit.json'),
        clean_manifest=str(LOGS/'clean_manifest.json'), clean_manifest_sha256=digest(LOGS/'clean_manifest.json'),
        approved_additions=str(LOGS/'approved_additions.json'), approved_additions_sha256=digest(LOGS/'approved_additions.json'),
        formal_allowed=not errors, training_started=False)
    write_json(TARGET/'data.provenance.json', new_provenance)
    lines = ['# clean_v2 数据验收', '',
        '按用户最终批准，将28个新增裂纹框写入独立副本；原始ID 7 → clean ID 2（liewenshe），7类顺序不变。', '',
        '| Split | 图片数 | 修改标签的图片数 | 新增裂纹框 |', '|---|---:|---:|---:|']
    lines += [f"| {s} | {stats[(s,'images')]} | {stats[(s,'changed_images')]} | {stats[(s,'added_boxes')]} |" for s in ('train','val','test')]
    lines += ['', '**合计修改25张图片标签，新增28个裂纹框；图片内容未改动。**', '',
        '逐文件验证YOLO五字段格式、类别ID 0–6、有限归一化坐标、正宽高、框边界、重复标注行、图片解码和图像/标签配对；检查结果见[reaudit.json](reaudit.json)。',
        '每个原标注行按原顺序和原字节保留，修改文件仅追加类别2；其他类别、26号原有裂纹框及16/22/28号的其他类别标注保留。',
        '4368张图片全部为物理副本；train/val/test划分不变，测试图片及标签逐字节相同，跨集合字节/像素完全重复为0。测试集仅核对数据完整性，未运行模型或使用测试指标调参。', '',
        '[独立配置](../../datasets/clean_v2/data.yaml) / [逐图修改清单](changes.csv) / [每类统计](class_counts.csv) / [已批准框快照](approved_additions.json)', '',
        '批准框的归一化坐标为写入依据，保留到12位小数；历史建议图的整数边界仅为绘图时向外取整。没有重新推断、移动、合并或替换已通过框。',
        '原始数据与clean_v1不修改；clean_v1所有保留图片/标签及根配置哈希前后核对一致。隔离样本未加入clean_v2，仍由clean_v1隔离目录和审计记录保管。',
        f'本轮有{len(legacy_pixel_differences)}张图的当前RGB哈希与旧审计记录不同，旧解码环境原因未复现；已验证这些图的文件SHA-256仍与旧清单一致，且当前同一环境解码的clean_v1/clean_v2尺寸和像素字节完全相同。具体记录见legacy_pixel_hash_differences.json。',
        '本轮只验收数据，未训练。患者身份未知及原有未决同集合近重复等限制沿用clean_v1；本次仅完成这28张候选范围内的人工裂纹复核，不能据此推定其余数据不存在漏标。', '']
    (LOGS/'README.md').write_text('\n'.join(lines), encoding='utf-8')
    shutil.copyfile(Path(__file__), LOGS/'build_clean_v2_snapshot.py')
    if errors:
        raise RuntimeError('Data audit failed; review the report before using clean_v2')
    load_config(TARGET/'data.yaml')
    finalize_review(plan)
    write_json(LOGS/'build.json', dict(completed=True, modified_images=25, added_boxes=28,
        script_sha256=digest(__file__), config_sha256=digest(TARGET/'data.yaml'), source_metadata_sha256=immutable,
        review_finalized=True, training_started=False))
    print('clean_v2 completed and verified: 25 modified image labels, 28 added fissure boxes.', flush=True)
    print(f'Config: {TARGET / "data.yaml"}', flush=True)
    print('clean_v1, existing annotation rows, and test data preserved. Training not started.', flush=True)


if __name__=='__main__':
    main()
