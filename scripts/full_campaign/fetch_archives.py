#!/usr/bin/env python3
"""Copy a complete suite's verified raw archives from control storage to D:."""
import argparse
import concurrent.futures
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'runs/full20261009'


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def psquote(value):
    return "'" + value.replace("'", "''") + "'"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('suite', choices=['fp', 'bv', 'bv_lia', 'maxsmt'])
    suite = parser.parse_args().suite
    assert ROOT.as_posix().startswith('/mnt/d/'), 'Store bulk archives directly on D:'
    ps = shutil.which('powershell.exe')
    assert ps
    records = json.loads((OUT / (suite + '-archives.json')).read_text())
    count = len((ROOT / 'benchmarks/full_public/manifests' / (suite + '.jsonl')).read_text().splitlines())
    assert sum(r['runs'] for r in records) == count
    assert len({r['host'] for r in records}) == len(records)
    space_command = 'Get-Volume -DriveLetter C,D | Select-Object DriveLetter,SizeRemaining,Size | ConvertTo-Json -Compress'
    probe = subprocess.run([ps, '-NoProfile', '-NonInteractive', '-Command', space_command],
                           capture_output=True, text=True, check=True)
    volumes = json.loads(probe.stdout)
    pending_bytes = 0
    for record in records:
        expected = 'runs/full20261009/raw/' + suite + '-' + record['host'] + '.tar.gz'
        assert record['path'] == expected and re.fullmatch(r'(?:panda|tiger)\d+', record['host'])
        path = ROOT / record['path']
        if path.exists():
            assert path.stat().st_size == record['bytes'] and sha(path) == record['sha256'], path
        else:
            pending_bytes += record['bytes']
    assert next(v['SizeRemaining'] for v in volumes if v['DriveLetter'] == 'D') > pending_bytes
    assert shutil.disk_usage(ROOT).free > pending_bytes
    print('HOST_DISK_CHECK', json.dumps(volumes), 'download_bytes', pending_bytes, flush=True)

    def fetch(record):
        path = ROOT / record['path']
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temporary = path.with_suffix('.download')
            windows = 'D:/' + temporary.relative_to('/mnt/d').as_posix()
            source = 'jiafq@192.168.20.110:/pub/data/jiafq/omt-survey-exp/' + record['path']
            command = '& scp -O -o BatchMode=yes -o ConnectTimeout=15 ' + psquote(source) + ' ' + psquote(windows)
            print('FETCH', path.name, record['bytes'], flush=True)
            subprocess.run([ps, '-NoProfile', '-NonInteractive', '-Command', command],
                           check=True, timeout=7200)
            assert temporary.stat().st_size == record['bytes'] and sha(temporary) == record['sha256']
            temporary.replace(path)
        print('VERIFIED_LOCAL', path.name, record['runs'], 'runs', flush=True)
        return record

    done = []
    target = OUT / (suite + '-local-archives.json')
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(fetch, record) for record in records]
        for future in concurrent.futures.as_completed(futures):
            done.append(future.result())
            report = dict(suite=suite, observed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                          expected_inputs=count, local_complete=len(done)==len(records),
                          disk_before=volumes, archives=sorted(done, key=lambda r: r['host']))
            temporary = target.with_suffix('.tmp')
            temporary.write_text(json.dumps(report, indent=2) + '\n')
            temporary.replace(target)
    assert sum(r['runs'] for r in done) == count
    print('ALL_RAW_ARCHIVES_LOCAL', suite, count, 'inputs', flush=True)


if __name__ == '__main__':
    main()
