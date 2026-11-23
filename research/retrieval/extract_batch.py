"""Small, resumable real textbook batch using the existing local Qwen weights."""
import argparse
import csv
import json
import re
import time
from pathlib import Path
from .graph import validate_candidate
from .io_utils import digest, read_json, rows, write_json, write_rows
from .quality import quality

QUALIFIERS = ['可见', '多见', '常见', '可能', '多为', '常为', '一般', '往往', '提示', '不一定', '未必', '不能']


def exact_quote(quote, text):
    if not isinstance(quote, str) or not quote.strip():
        raise ValueError('Support quote must be nonempty')
    if quote in text:
        return quote
    # Restore original OCR whitespace; never change any actual character to make a quote fit.
    positions = [i for i, char in enumerate(text) if not char.isspace()]
    compact = ''.join(text[i] for i in positions)
    wanted = ''.join(quote.split())
    offset = compact.find(wanted)
    if not wanted or offset < 0:
        raise ValueError('Support quote is not in the source chunk')
    return text[positions[offset]:positions[offset+len(wanted)-1]+1]


def prepare_candidate(triple, chunk, terms, model, revision):
    quote = exact_quote(triple['quote'], chunk['text'])
    condition = triple.get('condition', '')
    if not isinstance(condition, str) or (condition and condition not in quote):
        raise ValueError('Applicability condition must be an exact part of the support quote or empty')
    condition_origin = 'qwen' if condition else 'not_stated_or_requires_review'
    if not condition:
        clause = re.match(r'^([^。；]{1,45}(?:者|时|见之))[，,]', quote)
        if clause:
            condition, condition_origin = clause[1], 'literal_source_clause'
    raw = {k: triple[k].strip() for k in ['subject', 'predicate', 'object']}
    value = {k: terms.get(v, v) if k != 'predicate' else v for k, v in raw.items()}
    value.update({k+'_raw': v for k, v in raw.items()})
    warnings = []
    if raw['subject'] not in quote:
        warnings.append('支持句未重复头实体名称，请结合片段标题核对主体')
    if any(q in raw['predicate'] and q not in quote for q in QUALIFIERS):
        warnings.append('谓词含原句未出现的限定语，需核对关系措辞')
    value.update(schema_version=2, condition=condition, condition_origin=condition_origin,
                 qualifiers=[q for q in QUALIFIERS if q in quote],
                 quote=quote, chunk_id=chunk['chunk_id'], source_title=chunk['source_title'],
                 edition=chunk.get('edition'), location=chunk['location'], source_hash=digest(chunk),
                 status='pending', reviewer=None, reviewed_at=None, model=model, model_revision=revision,
                 normalization_version='terms-v1', is_demo=False, source_text=chunk['text'], review_warnings=warnings)
    value['candidate_id'] = validate_candidate(value, {chunk['chunk_id']: chunk})
    return value


def export_review(candidates, path):
    columns = ['candidate_id','subject','predicate','object','condition','qualifiers','quote',
               'chunk_id','source_title','edition','pdf_page','printed_page','chapter','status','reviewer',
               'review_warnings','source_text']
    with open(path, 'w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, columns)
        writer.writeheader()
        for c in candidates:
            value = {k: c.get(k) for k in columns}
            value.update({k: c['location'].get(k) for k in ['pdf_page','printed_page','chapter']})
            value['qualifiers'] = '；'.join(c.get('qualifiers', []))
            value['review_warnings'] = '；'.join(c.get('review_warnings', []))
            writer.writerow(value)


def run(corpus, output, limit=8):
    from .local_qwen import LocalQwen
    chunks = rows(corpus)
    selected = [c for c in chunks if quality(c)['retrieval_eligible'] and '舌诊' in c['location']['chapter']
                and 100 < len(c['text']) < 350 and '【临床意义】' in c['text']
                and any(q in c['text'] for q in ['多见','可见','常见','主','提示'])][:limit]
    if not selected:
        raise ValueError('No clear clinical tongue-diagnosis chunks selected')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_rows(output/'selected-chunks.jsonl', selected)
    terms = read_json(Path(__file__).with_name('terms.json'))
    qwen = LocalQwen()
    candidates = {c['candidate_id']: c for c in rows(output/'candidates.jsonl')} if (output/'candidates.jsonl').exists() else {}
    report = {'model': qwen.model_id, 'revision': qwen.revision, 'corpus_hash': digest(chunks),
              'selected_chunk_ids': [c['chunk_id'] for c in selected], 'chunks': [], 'errors': []}
    for chunk in selected:
        cid = chunk['chunk_id']
        raw_path = output/'raw'/f'{cid}.json'
        started = time.perf_counter()
        prompt = ('从以下中医教材片段抽取最多4条明确的舌象与证候/临床意义关系。只依据本片段，不推理，不补充。'
                  '保留“多见”“可见”“常见”“可能”等限定语，不把提示关系改为确定诊断。'
                  '返回JSON对象：{"triples":[{"subject":"原文头实体","predicate":"原文关系或主/提示/多见于",'
                  '"object":"原文尾实体","condition":"quote中的逐字适用条件，无则空字符串",'
                  '"quote":"完整的逐字支持原句，包含实体、限定语和条件"}]}。'
                  'quote必须完整存在于原文；没有明确关系返回空数组。不要输出Markdown。\n教材片段：\n'+chunk['text'])
        try:
            candidates = {key: value for key, value in candidates.items()
                          if value['chunk_id'] != cid or value['status'] != 'pending'}
            if raw_path.exists():
                raw = read_json(raw_path)['raw']
            else:
                raw = qwen(prompt)
                write_json(raw_path, {'chunk_id': cid, 'raw': raw, 'seconds': time.perf_counter()-started})
            parsed = json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip()))
            accepted = 0
            triples = parsed if isinstance(parsed, list) else parsed['triples']
            for triple in triples:
                try:
                    value = prepare_candidate(triple, chunk, terms, qwen.model_id, qwen.revision)
                    candidates.setdefault(value['candidate_id'], value)
                    accepted += 1
                except (ValueError, KeyError, TypeError) as exc:
                    report['errors'].append({'chunk_id': cid, 'error': str(exc), 'triple': triple})
            report['chunks'].append({'chunk_id': cid, 'accepted': accepted, 'seconds': time.perf_counter()-started})
            print(f'{cid}: validated={accepted}', flush=True)
        except Exception as exc:
            report['errors'].append({'chunk_id': cid, 'error': str(exc)[:400]})
            print(f'{cid}: failed={type(exc).__name__}', flush=True)
        write_rows(output/'candidates.jsonl', candidates.values())
        write_json(output/'run.json', report)
    export_review(list(candidates.values()), output/'review.csv')
    print(f'pending_candidates={len(candidates)}, anomalies={len(report["errors"])}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', default='research/retrieval/data/textbook/chunks.jsonl')
    parser.add_argument('--out', default='research/retrieval/data/qwen-batch')
    parser.add_argument('--limit', type=int, default=8)
    args = parser.parse_args()
    run(args.corpus, args.out, args.limit)
