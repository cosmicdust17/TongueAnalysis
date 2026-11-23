"""Wait for this local training process, then run the frozen validation comparison."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'results'/'comparison'/'clean-v1-vs-clean-v2'
EXIT_FILE = OUTPUT/'training_exit_code.txt'


def state(status, **details):
    (OUTPUT/'experiment_status.json').write_text(json.dumps(dict(status=status, **details), indent=2), encoding='utf-8')


def main():
    status_path = OUTPUT/'experiment_status.json'
    completed = status_path.exists() and json.loads(status_path.read_text(encoding='utf-8')).get('status') == 'complete'
    if completed and (OUTPUT/'comparison.json').exists():
        raise FileExistsError('Comparison already completed; preserve results')
    state('waiting_for_training', train_run='clean-v2-yolo11n-seed42', test_evaluated=False)
    while not EXIT_FILE.exists():
        time.sleep(15)
    code = EXIT_FILE.read_text(encoding='ascii').strip()
    if code != '0':
        state('training_failed', exit_code=code, test_evaluated=False)
        raise RuntimeError('Training did not finish successfully; comparison was not run')
    run = ROOT/'results'/'formal'/'clean-v2-yolo11n-seed42'
    if not all((run/name).is_file() for name in ('actual_parameters.json', 'weights/best.pt', 'weights/last.pt')):
        raise FileNotFoundError('Training success marker present but required outputs are missing')
    state('comparing_validation', test_evaluated=False)
    print('Training finished. Starting frozen clean_v2 validation comparison.', flush=True)
    code = subprocess.call([sys.executable, '-u', str(ROOT/'evaluation'/'compare_clean_v2.py')], env=os.environ.copy())
    state('complete' if code == 0 else 'comparison_failed', exit_code=code, test_evaluated=False)
    if code:
        raise RuntimeError('Comparison failed; inspect comparison_console.log')
    print('Experiment complete. Comparison table and example images saved.', flush=True)


if __name__ == '__main__':
    main()
