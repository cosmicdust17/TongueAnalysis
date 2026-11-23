"""Prepare this review round without writing to the graph database."""
from collections import Counter
from datetime import datetime, timezone

from openpyxl import load_workbook

from .extract_batch import exact_quote
from .graph import prepare_reviewed, validate_candidate
from .io_utils import file_hash, read_json, rows, write_json, write_rows
from .workbook_review import AUDIT, CANDIDATES, CORPUS, apply_workbook

FOCUS = 'rel_fac815a69cc0c5cab65e05d1'
MERGES = {
    'rel_f17a47ec861f05c90d5283ce': 'rel_fd36775f2d7b73a34588d8ad',
    'rel_dc19db2f38bacab0051ef1f6': 'rel_6a920fea475c97000f9185d1',
}
SPLITS = {
    'rel_5e43c29953c09278cddd8ecc': [
        ('强硬舌', '多因', '外感热病，邪入心包', '强硬舌多因外感热病，邪入心包，扰乱心神，致舌无主宰', ''),
        ('热盛伤津，筋脉失养', '可致', '强硬舌', '或热盛伤津，筋脉失养，使舌体失其柔和之性，故见强硬', ''),
        ('肝风夹痰，风痰阻滞舌体脉络', '亦可使', '舌体强硬不灵', '或肝风夹痰，风痰阻滞舌体脉络等，亦可使舌体强硬不灵。', ''),
    ],
    'rel_619d7d17d13dda86b5616acf': [
        ('舌苔厚腻', '多为', '湿浊、痰饮、食积', '舌苔厚腻，多为湿浊、痰饮、食积', ''),
        ('舌苔白腻不燥', '多为', '脾虚湿困', '舌苔白腻不燥，自觉胸闷，多为脾虚湿困，阻滞气机', '自觉胸闷'),
        ('舌苔白腻而滑', '为', '痰浊、寒湿内阻', '舌苔白腻而滑者，为痰浊、寒湿内阻', ''),
        ('舌苔黏腻而厚', '是', '脾胃湿热', '舌苔黏腻而厚，口中发甜，是脾胃湿热，邪聚上泛', '口中发甜'),
        ('舌苔黄腻而厚', '为', '痰热、湿热、暑湿等邪内蕴', '舌苔黄腻而厚，为痰热、湿热、暑湿等邪内蕴', ''),
    ],
}
INPUT = AUDIT / '舌诊教材三元组审核表.xlsx'
OUTPUT = AUDIT / 'round-update'
REVIEWER = '本轮用户（对话确认）'
FOCUS_NOTE = '确认淡红舌可见于部分表证。部分为人工限定，原文及外感病见之条件照录。'


def stage():
    from copy import deepcopy

    checked = read_json(AUDIT / 'checked.json')
    existing = {row['candidate_id']: row for row in rows(CANDIDATES)}
    if checked.keys() != existing.keys():
        raise ValueError('审核记录与现有候选 ID 不一致')
    for candidate_id, audit in checked.items():
        if existing[candidate_id]['source_hash'] != audit['original']['source_hash']:
            raise ValueError(f'候选出处已变更：{candidate_id}')

    book = load_workbook(INPUT, read_only=True)
    try:
        workbook_decisions = {row[0]: list(row[2:5]) for row in book['候选审核'].iter_rows(min_row=5, max_col=5, values_only=True)
                              if row[0]}
    finally:
        book.close()
    if workbook_decisions.keys() != checked.keys():
        raise ValueError('审核表未覆盖本批候选 ID')

    audit = checked[FOCUS]
    audit['revision'].update(subject='淡红舌', predicate='可见于', object='表证', object_qualifier='部分')
    audit['reason'] = '按本轮人工意见改为“淡红舌可见于部分表证”。适用条件保留“外感病见之”，原书措辞保存在引文。'

    for duplicate_id, keep_id in MERGES.items():
        duplicate, keep = checked[duplicate_id], checked[keep_id]
        if duplicate['source']['chunk_id'] != keep['source']['chunk_id']:
            raise ValueError(f'合并涉及不同证据片段：{duplicate_id}')
        revision = keep['revision']
        quote = duplicate['original']['quote']
        if quote != revision['quote']:
            revision.setdefault('supporting_quotes', []).append(quote)
        keep.setdefault('merged_from', []).append(duplicate_id)
        duplicate['merged_into'] = keep_id

    for parent_id, proposals in SPLITS.items():
        chunk = checked[parent_id]['source']
        checked[parent_id]['split_proposals'] = []
        for subject, predicate, obj, quote, condition in proposals:
            quote = exact_quote(quote, chunk['text'])
            proposal = dict(schema_version=2, subject=subject, predicate=predicate, object=obj,
                            chunk_id=chunk['chunk_id'], quote=quote, condition=condition, qualifiers=[], status='pending')
            proposal['candidate_id'] = validate_candidate(proposal, {chunk['chunk_id']: chunk})
            checked[parent_id]['split_proposals'].append(proposal)

    disposition = {'建议保留': '保留', '建议修订': '修订', '建议拆分后再审': '待拆分复审', '建议不采纳': '排除'}
    for candidate_id, item in checked.items():
        item['disposition'] = '合并' if candidate_id in MERGES else disposition[item['recommendation']]
        item['human'] = workbook_decisions[candidate_id]
        revision = item.get('revision')
        if revision:
            chunk = item['source']
            revision['revision_id'] = validate_candidate(revision, {chunk['chunk_id']: chunk})
    checked[FOCUS]['human'] = ['批准修订', REVIEWER, FOCUS_NOTE]

    audit_path = OUTPUT / 'checked-round.json'
    release_path = OUTPUT / 'publish-candidates.jsonl'
    write_json(audit_path, checked)
    # Apply all decisions saved in the workbook to a copy, then apply this round's explicit direction.
    staged = OUTPUT / 'workbook-decisions.jsonl'
    write_rows(staged, existing.values())
    apply_workbook(INPUT, audit_path, staged)
    previous = {row['candidate_id']: row for row in rows(release_path)} if release_path.exists() else {}
    prepared = []
    for value in rows(staged):
        candidate_id = value['candidate_id']
        item = checked[candidate_id]
        state = item['disposition']
        value.update(disposition=state, disposition_reason=item['reason'])
        if item.get('revision'):
            value['proposed_revision'] = deepcopy(item['revision'])
        for field in ('merged_into', 'merged_from', 'split_proposals'):
            if field in item:
                value[field] = item[field]

        if candidate_id == FOCUS or state in {'合并', '排除'}:
            status = 'approved' if candidate_id == FOCUS else 'rejected'
            note = FOCUS_NOTE if candidate_id == FOCUS else item['reason']
            recorded = previous.get(candidate_id, {})
            at = recorded.get('reviewed_at') if recorded.get('status') == status else None
            value.update(status=status, reviewer=REVIEWER, review_note=note,
                         reviewed_at=at or datetime.now(timezone.utc).isoformat())
            if status == 'approved':
                value['reviewed_revision'] = deepcopy(item['revision'])
            else:
                value.pop('reviewed_revision', None)
        prepared.append(value)

    write_rows(release_path, prepared)
    _, values, approved = prepare_reviewed(CORPUS, release_path)
    report = {
        'workbook_sha256': file_hash(INPUT), 'candidate_count': len(values),
        'dispositions': dict(Counter(value['disposition'] for value in values)),
        'approval_statuses': dict(Counter(value['status'] for value in values)),
        'publishable_ids': [value['candidate_id'] for value in approved], 'neo4j_writes': 0,
        'merged_into': MERGES,
        'split_drafts': sum(len(item.get('split_proposals', [])) for item in checked.values()),
        'not_in_publish_batch': [{
            'candidate_id': value['candidate_id'], 'disposition': value['disposition'],
            'reason': value['disposition_reason'] if value['status'] == 'rejected' or value['disposition'] == '待拆分复审'
                      else '审核表中没有人工批准记录',
        } for value in values if value['status'] != 'approved'],
    }
    write_json(OUTPUT / 'preflight.json', report)
    return report


if __name__ == '__main__':
    import json

    print(json.dumps(stage(), ensure_ascii=False))
