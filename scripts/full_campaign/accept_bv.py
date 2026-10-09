#!/usr/bin/env python3
"""Accept the hashed public archive after the temporary relay finishes."""
import json
from pathlib import Path
import subprocess
import time
import prepare

root = prepare.ROOT
downloads = prepare.DATA / 'downloads'
progress = downloads / 'tacas16.relay.progress.json'
expected = '20636e89acc4f7d12e312dbe1bc86b98327b16ef9bf9b07469a4467a75979a22'
deadline = time.monotonic() + 3 * 3600
while True:
    record = json.loads(progress.read_text()) if progress.exists() else {}
    if record.get('error'):
        raise RuntimeError('Relay failed: ' + record['error'])
    if record.get('complete'):
        break
    if time.monotonic() > deadline:
        raise TimeoutError('Relay has not completed; no input accepted')
    time.sleep(10)

assert record['bytes'] == 1552395059 and record['sha256'] == expected
archive = downloads / 'tacas16.relay.download'
assert archive.stat().st_size == record['bytes'] and prepare.sha(archive) == expected
target = downloads / 'tacas16.tar.gz'
if target.exists():
    # The failed slow transfer is retained; its writer was stopped explicitly.
    partial = downloads / 'tacas16.scp.partial'
    assert not partial.exists(), 'Inspect the existing partial transfer first'
    target.rename(partial)
archive.rename(target)
(downloads / 'tacas16.tar.gz.sha256').write_text(expected + '\n')
print('BV_ARCHIVE_VERIFIED', record['bytes'], expected, flush=True)
subprocess.run(['python3', str(root / 'scripts/full_campaign/launch_ready.py'), 'bv'],
               cwd=root, check=True)
