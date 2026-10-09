#!/usr/bin/env python3
"""Download complete original public artifacts atomically; never select instances."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'benchmarks/full_public/downloads'
FP_DIGEST = '5c868ea5510ea04ec6fa0b495c2b421326f33491a176d2e52cf350ec39b0e182'
SOURCES = {
    'PairLS.rar': 'https://github.com/LS-OptSMT/PairLS/releases/download/PairLS/PairLS.rar',
    'tacas16.tar.gz': 'https://drive.usercontent.google.com/download?id=0B0zXW5t7in-felhlbjZDZDZKN3M&export=download&confirm=t&resourcekey=0-ZE5pkUVyuOsK7wXhCKOrLw',
}


def download(name, url, headers=None, expected=None):
    DEST.mkdir(parents=True, exist_ok=True)
    target = DEST / name
    # The completion marker distinguishes a verified download from an interrupted transfer.
    marker = target.with_name(target.name + '.sha256')
    if target.exists() and marker.exists():
        actual = hashlib.file_digest(target.open('rb'), 'sha256').hexdigest()
        assert actual == marker.read_text().strip()
        if expected:
            assert actual == expected
        return dict(name=name, bytes=target.stat().st_size, sha256=actual, url=url)
    partial = target.with_name(target.name + '.download')
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=120) as response, partial.open('wb') as out:
        content_type = response.headers.get('Content-Type', '')
        assert 'text/html' not in content_type, (name, content_type)
        h = hashlib.sha256()
        while block := response.read(1024 * 1024):
            out.write(block)
            h.update(block)
    actual = h.hexdigest()
    if expected:
        assert actual == expected
    partial.replace(target)
    marker.write_text(actual + '\n')
    row = dict(name=name, bytes=target.stat().st_size, sha256=actual, url=url)
    print(json.dumps(row), flush=True)
    return row


def fetch_fp():
    repo = 'patricktrentin88/jar2020_floatingpoint_test'
    with urllib.request.urlopen('https://auth.docker.io/token?service=registry.docker.io&scope=repository:' + repo + ':pull', timeout=60) as r:
        token = json.load(r)['token']
    return download('fp-layer.tar.gz', f'https://registry-1.docker.io/v2/{repo}/blobs/sha256:{FP_DIGEST}',
                    {'Authorization': 'Bearer ' + token}, FP_DIGEST)


def main():
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        tasks = [pool.submit(fetch_fp)]
        tasks += [pool.submit(download, name, url) for name, url in SOURCES.items()]
        rows = [t.result() for t in tasks]
    (DEST.parent / 'source-downloads.json').write_text(json.dumps(rows, indent=2) + '\n')


if __name__ == '__main__':
    main()
