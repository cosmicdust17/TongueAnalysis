import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Independent local textbook retrieval pipeline')
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('--pdf', required=True)
    inspect.add_argument('--out', required=True)
    inspect.add_argument('--pages', required=True, help='1,2,13-15 (one-based PDF pages)')
    inspect.add_argument('--ocr', action='store_true')
    extract = commands.add_parser('extract')
    extract.add_argument('--pdf', required=True)
    extract.add_argument('--plan', required=True)
    extract.add_argument('--out', required=True)
    for command in ('index', 'query', 'evaluate', 'ingest'):
        p = commands.add_parser(command)
        p.add_argument('--index', required=True)
        if command != 'ingest':
            p.add_argument('--embedding', default='BAAI/bge-small-zh-v1.5')
            p.add_argument('--reranker', default='BAAI/bge-reranker-base')
        if command == 'index':
            p.add_argument('--corpus', required=True)
            p.add_argument('--batch-size', type=int, default=32)
        if command in ('query', 'evaluate'):
            p.add_argument('--k', type=int, default=5)
            p.add_argument('--candidates', type=int, default=40)
        if command == 'query':
            p.add_argument('--symptoms', default='')
            p.add_argument('--tongue-features', default='')
            p.add_argument('--out', required=True)
        if command == 'evaluate':
            p.add_argument('--labels', required=True)
            p.add_argument('--out', required=True)
            p.add_argument('--split', choices=['test', 'validation'], default='test')
            p.add_argument('--allow-demo', action='store_true')
    candidates = commands.add_parser('graph-extract')
    candidates.add_argument('--corpus', required=True)
    candidates.add_argument('--out', required=True)
    candidates.add_argument('--endpoint', default='http://127.0.0.1:11434/v1')
    candidates.add_argument('--model', default='qwen2.5:7b')
    review = commands.add_parser('review')
    review.add_argument('--file', required=True)
    review.add_argument('--id', required=True)
    review.add_argument('--status', choices=['approved', 'rejected'], required=True)
    review.add_argument('--reviewer', required=True)
    publish = commands.add_parser('graph-import')
    publish.add_argument('--corpus', required=True)
    publish.add_argument('--file', required=True)
    training = commands.add_parser('train')
    training.add_argument('kind', choices=['embedding', 'reranker'])
    training.add_argument('--corpus', required=True)
    training.add_argument('--labels', required=True)
    training.add_argument('--out', required=True)
    training.add_argument('--model', required=True)
    training.add_argument('--epochs', type=int, default=1)
    training.add_argument('--batch-size', type=int, default=8)
    args = parser.parse_args()
    if args.command == 'inspect':
        from .extract import inspect_pdf
        pages = []
        for part in args.pages.split(','):
            bounds = [int(v) for v in part.split('-')]
            pages.extend(range(bounds[0], bounds[-1]+1))
        inspect_pdf(args.pdf, args.out, pages, args.ocr)
    elif args.command == 'extract':
        from .extract import extract
        extract(args.pdf, args.plan, args.out)
    elif args.command == 'ingest':
        from .neo import NeoStore
        store = NeoStore()
        try:
            print(json.dumps(store.ingest(args.index)))
        finally:
            store.close()
    elif args.command in ('index', 'query', 'evaluate'):
        from .core import Models, LocalIndex, build_vectors, retrieve
        from .io_utils import write_json
        models = Models(args.embedding, args.reranker)
        if args.command == 'index':
            print(json.dumps(build_vectors(args.corpus, args.index, models, args.batch_size)))
        elif args.command == 'query':
            result = retrieve(LocalIndex(args.index, models), models, args.symptoms, args.tongue_features, args.candidates, args.k)
            write_json(args.out, result)
            print(f"evidence={len(result['evidence'])}, elapsed_ms={result['elapsed_ms']}")
        else:
            from .evaluation import evaluate
            result = evaluate(LocalIndex(args.index, models), models, args.labels, args.out, args.k, args.candidates, args.split, args.allow_demo)
            print(json.dumps({k: {s: v for s, v in r.items() if s != 'queries'} for k, r in result['modes'].items()}))
    elif args.command == 'graph-extract':
        from .graph import extract_candidates
        extract_candidates(args.corpus, args.out, args.endpoint, args.model)
    elif args.command == 'review':
        from .graph import review
        review(args.file, args.id, args.status, args.reviewer)
    elif args.command == 'graph-import':
        from .graph import import_reviewed
        from .neo import NeoStore
        store = NeoStore()
        try:
            print(import_reviewed(store, args.corpus, args.file))
        finally:
            store.close()
    elif args.command == 'train':
        from .training import train
        train(args.kind, args.corpus, args.labels, args.out, args.model, args.epochs, args.batch_size)


if __name__ == '__main__':
    main()
