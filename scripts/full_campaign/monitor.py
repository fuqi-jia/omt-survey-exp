#!/usr/bin/env python3
"""Maintain coverage snapshots and archive finished suites on the control node."""
import datetime
import fcntl
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'runs/full20261009'
lock = (OUT / 'monitor.lock').open('a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
completed_archives = set()
while True:
    with (OUT / 'snapshot.log').open('w') as log:
        result = subprocess.run(['python3', str(ROOT / 'scripts/full_campaign/snapshot.py')],
                                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        print('Snapshot needs investigation', datetime.datetime.now(datetime.timezone.utc).isoformat(), flush=True)
        time.sleep(120)
        continue
    status = json.loads((OUT / 'coverage-progress.json').read_text())
    all_ready = len(status['experiments']) == 4
    for experiment in status['experiments']:
        suite = experiment['suite']
        print(suite, experiment['platform_counts'], 'audit_errors', len(experiment['errors']),
              'disagreements', len(experiment['objective_disagreements']), flush=True)
        all_ready = all_ready and experiment['all_inputs_completed']
        if experiment['all_inputs_completed'] and suite not in completed_archives:
            with (OUT / (suite + '-archive.log')).open('a') as log:
                result = subprocess.run(['/usr/bin/python3.14', str(ROOT / 'scripts/full_campaign/archive_results.py'), suite],
                                        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode == 0:
                completed_archives.add(suite)
            else:
                print(suite, 'archive needs investigation; existing source logs preserved', flush=True)
    if all_ready and len(completed_archives) == 4:
        with (OUT / 'summarize.log').open('w') as log:
            result = subprocess.run(['python3', str(ROOT / 'scripts/full_campaign/summarize.py')],
                                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        result.check_returncode()
        print('COMPLETE: all four suites covered and archived', flush=True)
        break
    time.sleep(120)
