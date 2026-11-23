"""Select the default detector for NEW reports; restart model service afterwards."""
import argparse
from pathlib import Path
from dotenv import set_key

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('variant', choices=['clean_v1', 'clean_v2'])
args = parser.parse_args()
run = 'clean-v1-yolo11n-seed42' if args.variant == 'clean_v1' else 'clean-v2-yolo11n-seed42'
weights = root / 'research/results/formal' / run / 'weights/best.pt'
data = root / 'research/datasets' / args.variant / 'data.yaml'
if not weights.is_file() or not data.is_file():
    raise SystemExit('Selected weights or class mapping unavailable; no configuration changed')
set_key(root.parent / '.env', 'MODEL_WEIGHTS', str(weights))
set_key(root.parent / '.env', 'MODEL_DATA_YAML', str(data))
print('Selected:', args.variant, '; restart model service to apply. Existing report snapshots are unchanged.')
