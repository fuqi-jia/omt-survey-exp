#!/usr/bin/env python3
"""Finish preparation, validate the entire suite, then submit once to ExperimentOS."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import prepare

ROOT = prepare.ROOT
OUT = ROOT / 'runs/full20261009'
EOS = '/pub/data/jiafq/experimentos/eos'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('suite', choices=['fp', 'bv'])
    ap.add_argument('--wait-pid', type=int)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    lock = (OUT / (args.suite + '-pipeline.lock')).open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = {'suite': args.suite, 'pid': os.getpid(), 'steps': [], 'finished': False}
    state_path = OUT / (args.suite + '-pipeline.json')

    def save():
        state['updated_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        state_path.write_text(json.dumps(state, indent=2) + '\n')

    def run(command, cwd=ROOT, log=None):
        step = {'command': command, 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        state['steps'].append(step)
        save()
        if log:
            with (OUT / log).open('w') as stream:
                result = subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
        else:
            result = subprocess.run(command, cwd=cwd)
        step['returncode'] = result.returncode
        step['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save()
        result.check_returncode()

    try:
        if args.wait_pid:
            state['waiting_for_pid'] = args.wait_pid
            save()
            while Path('/proc', str(args.wait_pid), 'cmdline').exists():
                if not Path('/proc', str(args.wait_pid), 'cmdline').read_bytes():
                    break  # Reaped work awaiting its parent; no source writer remains.
                time.sleep(10)
            state.pop('waiting_for_pid')
        if args.suite == 'fp':
            run(['python3', str(ROOT / 'scripts/full_campaign/finalize_fp.py')], log='fp-finalize.log')
            suites = ['fp']
        else:
            archive = ROOT / 'benchmarks/full_public/downloads/tacas16.tar.gz'
            assert archive.stat().st_size == 1552395059
            assert prepare.sha(archive) == '20636e89acc4f7d12e312dbe1bc86b98327b16ef9bf9b07469a4467a75979a22'
            run(['python3', str(ROOT / 'scripts/full_campaign/prepare.py'), 'bv'], log='bv-prepare.log')
            suites = ['bv', 'bv_lia']
        for suite in suites:
            run(['python3', str(ROOT / 'scripts/full_campaign/validate_inputs.py'), suite], log=suite+'-parse.log')
            run(['python3', str(ROOT / 'scripts/full_campaign/spec.py'), suite], log=suite+'-spec.log')
            name = 'jos-full-' + suite + '-20261009-r1'
            con = sqlite3.connect('file:/pub/data/jiafq/eos/eos.db?mode=ro', uri=True)
            existing = con.execute('select id from experiment where name=?', (name,)).fetchone()
            con.close()
            if existing:
                raise RuntimeError('Already submitted: ' + name + ' / ' + existing[0])
            command = [EOS, 'submit', str(OUT / (suite + '.yaml'))]
            run(command + ['--dry-run'], cwd='/pub/data/jiafq/experimentos', log=suite+'-dry-run.log')
            run(command + ['--yes'], cwd='/pub/data/jiafq/experimentos', log=suite+'-submit.log')
        state['finished'] = True
    except Exception as error:
        state['error'] = str(error)
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
