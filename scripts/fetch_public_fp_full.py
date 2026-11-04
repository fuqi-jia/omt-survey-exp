#!/usr/bin/env python3
"""Fetch the pinned, published FP data layer and extract the complete o300 suite.

No container execution or bulk tar extraction. Only named data files are copied.
The original artifact is linked by Trentin & Sebastiani, JAR 2021,
https://doi.org/10.1007/s10817-021-09600-4.
"""
import collections
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1] / 'benchmarks/public_fp'
REPOSITORY = 'patricktrentin88/jar2020_floatingpoint_test'
IMAGE_DIGEST = 'sha256:2f02171c8b6f8c2d2d2ecd2286208fdac965055964c3aac44096a069418c2589'
LAYER_DIGEST = 'sha256:5c868ea5510ea04ec6fa0b495c2b421326f33491a176d2e52cf350ec39b0e182'
LAYER_SIZE = 88795760
PREFIX = 'data/floatingpoint_test/o300/'
RULE = 'All 1120 native o300 instances; no subsampling'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    archive = ROOT / 'upstream-layer.tar.gz'
    if not archive.exists():
        url = ('https://auth.docker.io/token?service=registry.docker.io'
               f'&scope=repository:{REPOSITORY}:pull')
        with urllib.request.urlopen(url, timeout=60) as response:
            token = json.load(response)['token']
        headers = {'Authorization': 'Bearer ' + token}
        req = urllib.request.Request(
            f'https://registry-1.docker.io/v2/{REPOSITORY}/manifests/{IMAGE_DIGEST}',
            headers=dict(headers, Accept='application/vnd.docker.distribution.manifest.v2+json'))
        with urllib.request.urlopen(req, timeout=60) as response:
            manifest_bytes = response.read()
        assert 'sha256:' + sha(manifest_bytes) == IMAGE_DIGEST
        manifest = json.loads(manifest_bytes)
        assert any(x['digest'] == LAYER_DIGEST and x['size'] == LAYER_SIZE
                   for x in manifest['layers'])
        req = urllib.request.Request(
            f'https://registry-1.docker.io/v2/{REPOSITORY}/blobs/{LAYER_DIGEST}', headers=headers)
        temporary = archive.with_suffix('.download')
        h = hashlib.sha256()
        with urllib.request.urlopen(req, timeout=60) as response, temporary.open('wb') as output:
            while block := response.read(1024 * 1024):
                output.write(block)
                h.update(block)
        assert temporary.stat().st_size == LAYER_SIZE
        assert 'sha256:' + h.hexdigest() == LAYER_DIGEST
        temporary.rename(archive)
    assert archive.stat().st_size == LAYER_SIZE
    assert 'sha256:' + sha(archive.read_bytes()) == LAYER_DIGEST

    selected = []
    with tarfile.open(archive, mode='r|gz') as tar:
        for member in tar:
            name = member.name
            if not (member.isfile() and name.startswith(PREFIX) and name.endswith('.smt2')
                    and not name.endswith(('.fp_to_bv.smt2', '.sat.smt2', '.unsat.smt2'))):
                continue
            group = name[len(PREFIX):].split('/')[0]
            sense = 'max' if name.endswith('.max.smt2') else 'min'
            assert name.endswith('.' + sense + '.smt2')
            data = tar.extractfile(member).read()
            relative = Path('full') / 'fp' / name[len(PREFIX):]
            path = ROOT / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                assert path.read_bytes() == data
            else:
                path.write_bytes(data)
            selected.append(dict(group=group, sense=sense, upstream=name,
                forms={'fp': dict(path=relative.as_posix(), sha256=sha(data))}))
    assert len(selected) == 1120
    counts = collections.Counter((x['group'], x['sense']) for x in selected)
    for row in selected:
        row['candidate_count'] = counts[row['group'], row['sense']]
    selected.sort(key=lambda x: (x['group'], x['sense'], x['upstream']))
    selection = dict(rule=RULE, population=1120, selected=selected)
    path = ROOT / 'selection-full.json'
    if path.exists():
        assert json.loads(path.read_text()) == selection
    else:
        path.write_text(json.dumps(selection, indent=2))
    print('Verified pinned artifact and extracted all 1120 native instances.')
    print('Derived formulations are generated from these native inputs by public_fp_full.py.')


if __name__ == '__main__':
    main()
