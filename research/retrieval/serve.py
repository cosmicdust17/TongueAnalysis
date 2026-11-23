import argparse
from .runtime_config import configure


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8011)
    args = parser.parse_args()
    configure()
    import uvicorn
    uvicorn.run('research.retrieval.service:app', host='127.0.0.1', port=args.port)
