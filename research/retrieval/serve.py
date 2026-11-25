import argparse
from .runtime_config import configure


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8011)
    parser.add_argument('--graph-only', action='store_true')
    args = parser.parse_args()
    configure()
    import uvicorn
    if args.graph_only:
        from .service import create_app
        app = create_app(graph_only=True)
    else:
        app = 'research.retrieval.service:app'
    uvicorn.run(app, host='127.0.0.1', port=args.port)
