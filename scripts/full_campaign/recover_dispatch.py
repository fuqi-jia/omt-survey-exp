#!/usr/bin/env python3
"""Resume this campaign after a known transient scheduler eligibility failure.

ExperimentOS checks requirements only on currently free slots. An empty usable
set can mark an already qualified experiment broken even while suitable hosts
are merely busy. Resume keeps all requirements, canary state and successful
runs intact; it neither changes cluster policy nor retries solver outcomes.
"""
import argparse
import datetime
import fcntl
import json
from pathlib import Path
import sqlite3
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'runs/full20261009'
EOS = '/pub/data/jiafq/experimentos/eos'
EXPECTED_ERROR = "没有任何可用机器满足 environment.require：{'python3': '>=3.9'}。详见控制面日志。"


def recover_once():
    con = sqlite3.connect('file:/pub/data/jiafq/eos/eos.db?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    candidates = []
    for exp in con.execute("select id,name,status,canary_state,error from experiment "
                           "where name like 'jos-full-%-20261009-r1'"):
        if (exp['status'] != 'broken' or exp['error'] != EXPECTED_ERROR
                or exp['canary_state'] != 'open'):
            continue
        counts = dict(con.execute('select status,count(*) from run where experiment_id=? group by status',
                                  (exp['id'],)))
        if counts.get('success', 0) and counts.get('pending', 0):
            candidates.append((dict(exp), counts))
    con.close()
    for exp, counts in candidates:
        command = [EOS, 'resume', exp['id'], '--yes']
        result = subprocess.run(command, cwd=Path(EOS).parent, text=True, capture_output=True)
        record = dict(observed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      experiment=exp, counts_before=counts, command=command,
                      returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
        with (OUT / 'dispatch-recovery.jsonl').open('a') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
        print(exp['name'], 'resume', result.returncode, counts, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    lock = (OUT / 'dispatch-recovery.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    while True:
        recover_once()
        if not args.watch:
            break
        time.sleep(120)
