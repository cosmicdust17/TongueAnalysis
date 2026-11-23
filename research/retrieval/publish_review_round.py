"""Publish the user-confirmed review round and capture real Neo4j and HTTP evidence."""
from datetime import datetime, timezone

import httpx
from openpyxl import load_workbook

from .graph import import_reviewed, prepare_reviewed
from .io_utils import read_json, rows, write_json, write_rows
from .neo import NeoStore
from .runtime_config import configure
from .stage_review_round import FOCUS, OUTPUT
from .workbook_review import CANDIDATES, CORPUS, apply_workbook

CHECKED = OUTPUT / 'checked-round.json'
MANIFEST = OUTPUT / 'publish-candidates.jsonl'
APPROVED = OUTPUT / 'batch-approved.jsonl'
WORKBOOK = OUTPUT / '舌诊教材三元组审核表-本轮修订.xlsx'
REVIEWER = '本轮用户（批量确认）'


def snapshot(store):
    records = store.run('MATCH (a:RetrievalEntity)-[r:RETRIEVAL_RELATION]->(b:RetrievalEntity) '
                        'RETURN elementId(r) AS element_id,a.name AS subject,b.name AS object,properties(r) AS relation')
    real = [row for row in records if not row['relation'].get('is_demo')]
    indexed = {row['relation']['candidate_id']: row for row in real}
    if len(indexed) != len(real):
        raise ValueError('Neo4j already contains duplicate candidate IDs')
    return indexed, len(records) - len(real)


def focus_check(values):
    matches = [row for row in values if row['source']['name'] == '淡红舌' and row['target']['name'] == '表证']
    if len(matches) != 1:
        raise ValueError('淡红舌与表证需有且仅有一条有效关系')
    edge = matches[0]
    relation, evidence = edge['relation'], edge['evidence']
    expected = (FOCUS, '可见于', '部分', '外感病见之', '外感病见之，多属表证', 'ch_da6bd816d1d39d82b8367bb1')
    actual = tuple(relation[key] for key in ('candidate_id', 'kind', 'object_qualifier', 'condition', 'quote', 'chunk_id'))
    if actual != expected or evidence['chunk_id'] != expected[-1] or evidence['location']['printed_page'] != 44:
        raise ValueError(f'重点关系或教材出处不匹配：{FOCUS}')
    return edge


def publish_round(base_url):
    configure()
    checks = read_json(CHECKED)
    values = rows(MANIFEST)
    book = load_workbook(WORKBOOK, read_only=True)
    try:
        sheet_rows = {row[0]: row for row in book['候选审核'].iter_rows(min_row=5, max_col=14, values_only=True) if row[0]}
    finally:
        book.close()
    candidate_ids = {v['candidate_id'] for v in values}
    if len(candidate_ids) != len(values) or candidate_ids != checks.keys() or candidate_ids != sheet_rows.keys():
        raise ValueError('审核表、原始核对记录和发布清单的候选 ID 不一致')

    now = datetime.now(timezone.utc).isoformat()
    for value in values:
        cid = value['candidate_id']
        state = value['disposition']
        decision = sheet_rows[cid][2]
        if state != sheet_rows[cid][10] or state != checks[cid]['disposition']:
            raise ValueError(f'审核表与发布清单的处理结论不一致：{cid}')
        if state not in {'修订', '保留'} or decision == '不批准／撤销':
            continue
        if state == '修订':
            revision = value['proposed_revision']
            if revision != checks[cid]['revision'] or revision['chunk_id'] != value['chunk_id']:
                raise ValueError(f'修订或出处发生变化：{cid}')
            value['reviewed_revision'] = revision
        if value['status'] != 'approved':
            value.update(status='approved', reviewer=REVIEWER, reviewed_at=now,
                         review_note='按用户本轮确认发布审核表中的最终版本。')

    write_rows(APPROVED, values)
    apply_workbook(WORKBOOK, CHECKED, APPROVED)
    chunks, values, prepared = prepare_reviewed(CORPUS, APPROVED)
    eligible_ids = {row['candidate_id'] for row in prepared}
    if len(eligible_ids) != len(prepared) or any(row['disposition'] not in {'修订', '保留'} for row in prepared):
        raise ValueError('预校验未通过：批准 ID 重复或包含暂缓条目')
    keys = [(row['subject'], row['predicate'], row['object'], row['condition'], row['object_qualifier']) for row in prepared]
    if len(set(keys)) != len(keys):
        raise ValueError('预校验未通过：有效关系语义重复')
    prepared_by_id = {v['candidate_id']: v for v in prepared}
    for item in values:
        target = item.get('merged_into')
        if target:
            edge = prepared_by_id[target]
            if edge['chunk_id'] != item['chunk_id'] or item['quote'] not in {edge['quote'], *edge['supporting_quotes']}:
                raise ValueError(f'合并缺少原引文或证据：{item["candidate_id"]}')

    store = NeoStore()
    try:
        before, demo_count = snapshot(store)
        source_rows = store.run('MATCH (c:RetrievalChunk) WHERE c.chunk_id IN $ids '
                                'RETURN c.chunk_id AS id,c.text AS text,'
                                'c.retrieval_eligible AS eligible', ids=sorted({row['chunk_id'] for row in prepared}))
        sources = {row['id']: row for row in source_rows}
        for row in prepared:
            source = sources.get(row['chunk_id'])
            if not source or not source['eligible'] or source['text'] != chunks[row['chunk_id']]['text']:
                raise ValueError(f'Neo4j 出处缺失、已隔离或与教材不一致：{row["candidate_id"]}')
        focus = prepared_by_id[FOCUS]
        if (focus['subject'], focus['predicate'], focus['object_qualifier'], focus['object'], focus['condition']) != (
                '淡红舌', '可见于', '部分', '表证', '外感病见之'):
            raise ValueError(f'批准版本与重点关系不一致：{FOCUS}')
        write_json(OUTPUT / 'publish-before.json', {'real_count': len(before), 'demo_count': demo_count,
                                                    'existing_batch_ids': sorted(eligible_ids & before.keys())})
        import_reviewed(store, CORPUS, APPROVED)
        first, first_demo = snapshot(store)
        if set(first) != (before.keys() - candidate_ids) | eligible_ids or first_demo != demo_count:
            raise ValueError('首次发布关系 ID 或隔离测试数据不一致')
        import_reviewed(store, CORPUS, APPROVED)
        repeat, repeat_demo = snapshot(store)
        if repeat != first or repeat_demo != demo_count:
            raise ValueError('重复发布改变了关系数量、属性或 Neo4j 关系 ID')
        db_edges = {edge['relation']['candidate_id']: edge for edge in store.graph(limit=500)}
        for cid, row in prepared_by_id.items():
            found = db_edges[cid]
            relation, evidence = found['relation'], found['evidence']
            actual = (found['source']['name'], relation['kind'], found['target']['name'], relation.get('object_qualifier'))
            expected = (row['subject'], row['predicate'], row['object'], row['object_qualifier'])
            if actual != expected or any(relation[key] != row[key] for key in ('quote','condition','chunk_id','supporting_quotes')):
                raise ValueError(f'Neo4j 关系方向、限定或出处与批准清单不一致：{cid}')
            if evidence['chunk_id'] != row['chunk_id'] or evidence['location'] != chunks[row['chunk_id']]['location']:
                raise ValueError(f'Neo4j 教材证据不匹配：{cid}')
        focus_check(list(db_edges.values()))
    finally:
        store.close()

    with httpx.Client(trust_env=False, timeout=15) as client:
        response = client.get(base_url.rstrip('/') + '/v1/graph', params={'limit': 500})
        response.raise_for_status()
        data = response.json()
        returned = {v['relation']['candidate_id']: v for v in data['relations']}
        if len(returned) != len(data['relations']) or returned != db_edges:
            raise ValueError('图谱接口响应与 Neo4j 发布关系不一致')
        focus_row = focus_check(data['relations'])
        focus_response = client.get(base_url.rstrip('/') + '/v1/graph', params={'chunk_id': focus_row['evidence']['chunk_id']})
        focus_response.raise_for_status()
        focus_check(focus_response.json()['relations'])
        write_json(OUTPUT / 'graph-api-response.json', data)
        write_json(OUTPUT / 'graph-api-focus-response.json', focus_response.json())

    for row in values:
        cid = row['candidate_id']
        published = cid in eligible_ids
        row['publication_status'] = 'published' if published else 'outside_batch'
        checks[cid]['publication_status'] = '已发布' if published else '本批未发布'
        if published:
            decision = '批准修订' if row['disposition'] == '修订' else '批准原案'
            checks[cid]['human'] = [decision, row['reviewer'], row.get('review_note', '')]
            row.setdefault('published_at', now)
    write_rows(MANIFEST, values)
    write_rows(APPROVED, values)
    write_rows(CANDIDATES, values)
    write_json(CHECKED, checks)

    outside = [{'candidate_id': v['candidate_id'], 'disposition': v['disposition'],
                'reason': v['disposition_reason'], 'merged_into': v.get('merged_into'),
                'draft_ids': [draft['candidate_id'] for draft in v.get('split_proposals', [])]}
               for v in values if v['candidate_id'] not in eligible_ids]
    report = {'before_real_count': len(before), 'after_real_count': len(first),
              'first_run_added': len(eligible_ids - before.keys()), 'first_run_existing': len(eligible_ids & before.keys()),
              'repeat_run_added': 0, 'repeat_run_existing': len(eligible_ids), 'repeat_element_ids_unchanged': True,
              'demo_count_unchanged': demo_count, 'http_url': str(response.url), 'http_status': response.status_code,
              'published_ids': sorted(eligible_ids), 'outside_batch': outside, 'failed_items': []}
    write_json(OUTPUT / 'publication-result.json', report)
    return report


if __name__ == '__main__':
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8014')
    args = parser.parse_args()
    print(json.dumps(publish_round(args.base_url), ensure_ascii=False))
