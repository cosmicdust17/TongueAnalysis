import argparse
from datetime import datetime, timezone
from pathlib import Path
from .io_utils import digest, read_json, rows, write_json


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Record a human OCR review without changing original text or vectors')
    parser.add_argument('--chunk-id', required=True)
    parser.add_argument('--reviewer', required=True)
    parser.add_argument('--status', required=True, choices=['approved','rejected'])
    parser.add_argument('--corpus', default='research/retrieval/data/textbook/chunks.jsonl')
    parser.add_argument('--file', default='research/retrieval/data/ocr-review.json')
    args = parser.parse_args()
    if not args.reviewer.strip():
        raise ValueError('A named human reviewer is required')
    chunks = {c['chunk_id']: c for c in rows(args.corpus)}
    chunk = chunks[args.chunk_id]
    path = Path(args.file)
    records = read_json(path) if path.exists() else {}
    records[args.chunk_id] = {'status': args.status, 'source_hash': digest(chunk),
                            'reviewer': args.reviewer, 'reviewed_at': datetime.now(timezone.utc).isoformat()}
    write_json(path, records)
    print('Review recorded. Re-ingest the index to synchronize Neo4j eligibility.')
