"""Export the checked evidence and apply explicit human decisions from the review workbook."""
from datetime import datetime, timezone
from pathlib import Path

from .extract_batch import QUALIFIERS, exact_quote
from .graph import validate_candidate
from .io_utils import digest, read_json, rows, write_json, write_rows
from .quality import quality
from .runtime_config import BASE

AUDIT = BASE / 'data/review-audit'
CANDIDATES = BASE / 'data/qwen-batch/candidates.jsonl'
CORPUS = BASE / 'data/textbook/chunks.jsonl'


def export():
    chunks = {item['chunk_id']: item for item in rows(CORPUS)}
    candidates = {item['candidate_id']: item for item in rows(CANDIDATES)}
    checks = {}
    for line in (AUDIT / 'notes.psv').read_text(encoding='utf-8').splitlines():
        candidate_id, recommendation, reason, *change = line.split('|')
        original = candidates[candidate_id]
        assert candidate_id not in checks
        chunk = chunks[original['chunk_id']]
        assert validate_candidate(original, chunks) == candidate_id and digest(chunk) == original['source_hash']
        checks[candidate_id] = dict(candidate_id=candidate_id, recommendation=recommendation, reason=reason,
                                    original=original, source=chunk, ocr=quality(chunk))
        if change:
            subject, predicate, obj, quote, *condition = change
            quote = exact_quote(quote, chunk['text'])
            revision = dict(schema_version=2, subject=subject, predicate=predicate, object=obj, quote=quote,
                            condition=exact_quote(condition[0], quote) if condition else '',
                            qualifiers=[word for word in [*QUALIFIERS, '多主', '多属', '亦可', '或'] if word in quote],
                            chunk_id=chunk['chunk_id'])
            revision['revision_id'] = validate_candidate(revision, chunks)
            checks[candidate_id]['revision'] = revision
    if checks.keys() != candidates.keys():
        raise ValueError('Review findings must cover every candidate exactly once')
    write_json(AUDIT / 'checked.json', checks)


def apply_workbook(workbook, checked_path, candidates_path):
    from openpyxl import load_workbook

    checked = read_json(checked_path)
    candidates = rows(candidates_path)
    by_id = {value['candidate_id']: value for value in candidates}
    book = load_workbook(workbook, read_only=True)
    changed = 0
    seen = set()
    try:
        sheet = book['候选审核']
        headers = next(sheet.iter_rows(min_row=4, max_row=4, max_col=5, values_only=True))
        if headers != ('候选 ID', '机器核对建议', '人工决策', '审核人', '人工备注'):
            raise ValueError('审核表列名或顺序已变更')
        for candidate_id, _recommendation, decision, reviewer, note, _original_text, revision_text in sheet.iter_rows(min_row=5, max_col=7, values_only=True):
            if not candidate_id:
                continue
            if candidate_id in seen or candidate_id not in checked or candidate_id not in by_id:
                raise ValueError(f'候选 ID 重复或已变更：{candidate_id}')
            seen.add(candidate_id)
            if not decision:
                continue
            original = by_id[candidate_id]
            entry = checked[candidate_id]
            if original['source_hash'] != entry['original']['source_hash']:
                raise ValueError(f'出处已变更：{candidate_id}')
            if decision not in {'批准原案', '批准修订', '不批准／撤销'} or not isinstance(reviewer, str) or not reviewer.strip():
                raise ValueError(f'请填写有效的人工决策和审核人：{candidate_id}')
            revision = entry.get('revision') if decision == '批准修订' else None
            if decision == '批准修订' and revision is None:
                raise ValueError(f'没有可批准的修订：{candidate_id}')
            if revision:
                if revision.get('object_qualifier'):
                    expected = ''.join(revision[key] for key in ('subject', 'predicate', 'object_qualifier', 'object'))
                else:
                    expected = ' → '.join(revision[key] for key in ('subject', 'predicate', 'object'))
                if revision_text != expected:
                    raise ValueError(f'审核表中的修订与待发布数据不一致：{candidate_id}')
            if original.get('disposition') in {'合并', '排除'} and decision != '不批准／撤销':
                raise ValueError(f'合并或排除的候选不能单独批准发布：{candidate_id}')
            fields = dict(status='rejected' if decision == '不批准／撤销' else 'approved',
                          reviewer=reviewer.strip(), review_note=note or '')
            if any(original.get(key) != value for key, value in fields.items()) or original.get('reviewed_revision') != revision:
                changed += 1
                original.update(fields, reviewed_at=datetime.now(timezone.utc).isoformat())
                if revision:
                    original['reviewed_revision'] = revision
                else:
                    original.pop('reviewed_revision', None)
    finally:
        book.close()
    if changed:
        write_rows(candidates_path, candidates)
    return changed


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('workbook', nargs='?', type=Path, help='Path to the filled workbook. Omit to export the audit data.')
    parser.add_argument('--review-file', type=Path, help='A staged publish-candidates file next to checked-round.json.')
    args = parser.parse_args()
    if args.workbook:
        checked = args.review_file.with_name('checked-round.json') if args.review_file else AUDIT / 'checked.json'
        count = apply_workbook(args.workbook, checked, args.review_file or CANDIDATES)
        print(f'已同步 {count} 条人工决策。')
    else:
        export()
