#!/usr/bin/env python3
"""Produce complete, hashed input manifests. No selection by size or solvability."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import time

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'benchmarks/full_public'
EXTRACTED = DATA / 'extracted'
OUT = ROOT / 'runs/full20261009'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while b := f.read(1024 * 1024):
            h.update(b)
    return h.hexdigest()


def extract(archive, dest, predicate=lambda m: True):
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as t:
        for m in t:
            if not m.isfile() or not predicate(m):
                continue
            p = dest / m.name
            if not p.resolve().is_relative_to(dest.resolve()):
                raise ValueError(m.name)
            p.parent.mkdir(parents=True, exist_ok=True)
            # Never assume that size alone establishes a complete transfer.
            with t.extractfile(m) as src, p.open('wb') as dst:
                while b := src.read(1024 * 1024):
                    dst.write(b)


def manifest(suite, paths, extra=None):
    rows = []
    for path in sorted(paths):
        relative = path.relative_to(ROOT).as_posix()
        rows.append(dict(id=hashlib.sha256(relative.encode()).hexdigest()[:20],
                         suite=suite, path=relative, bytes=path.stat().st_size,
                         sha256=sha(path)))
    assert len({r['id'] for r in rows}) == len(rows)
    directory = DATA / 'manifests'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (suite + '.jsonl')
    target.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    summary = dict(suite=suite, instances=len(rows), manifest_sha256=sha(target),
                   manifest=target.relative_to(ROOT).as_posix(), sampling=False,
                   total_bytes=sum(r['bytes'] for r in rows), extra=extra or {})
    (DATA / (suite + '-summary.json')).write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)
    return rows


def prepare_fp():
    base = EXTRACTED / 'fp'
    archive = DATA / 'downloads/fp-inputs.tar.xz'
    extract(archive, base)
    original = base / 'bin/run_translation.sh'
    code = original.read_text()
    # Include also the 31 original inputs marked UNSAT: they remain explicit
    # infeasible optimization tasks, rather than disappearing from coverage.
    guard = '''    if grep -q "status unsat" "${src_file}"; then
        echo -e "\\t(${PINK}warning${NORMAL}): status unsat in \\"${src_file}\\""
        return
    fi
'''
    pattern = r'    if grep -q "status unsat" "\$\{src_file\}"; then\n.*?\n        return\n    fi\n'
    code, count = re.subn(pattern, '', code, count=1, flags=re.S)
    assert count == 1
    all_statuses = base / 'bin/run_translation_all_statuses.sh'
    all_statuses.write_text(code)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / 'fp-generation.log').open('w') as log:
        subprocess.run(['bash', str(all_statuses), str(base/'bench'), str(base/'obench'), '0'],
                       cwd=base, stdout=log, stderr=subprocess.STDOUT, check=True)
    generated = sorted((base / 'obench').rglob('*.smt2'))
    # Cover the complete published o300 set as well. Exact corresponding copies
    # are aliases, not a second performance observation of the same input.
    aliases, published_extra = [], []
    for p in sorted((base / 'o300').rglob('*.smt2')):
        g = base / 'obench' / p.relative_to(base / 'o300')
        if g.exists() and sha(g) == sha(p):
            aliases.append(dict(published=p.relative_to(ROOT).as_posix(),
                                generated=g.relative_to(ROOT).as_posix(), sha256=sha(p)))
        else:
            published_extra.append(p)
    (DATA / 'fp-published-aliases.json').write_text(json.dumps(aliases, indent=2) + '\n')
    rows = manifest('fp', generated + published_extra,
                    dict(raw_source_files=len(list((base/'bench').rglob('*.smt2'))),
                         generated=len(generated), published=1120,
                         published_aliases=len(aliases), published_extra=len(published_extra),
                         original_generator_sha256=sha(original),
                         generator_sha256=sha(all_statuses),
                         patch='Retain original inputs labelled UNSAT; no random filter.'))
    assert len(aliases) + len(published_extra) == 1120
    assert rows


def prepare_bv():
    base = EXTRACTED / 'bv'
    archive = DATA/'downloads/bv-inputs.tar.xz'
    if not archive.exists():
        archive = DATA/'downloads/tacas16.tar.gz'
    extract(archive, base,
            lambda m: m.name.endswith(('.smt2', '/README.txt')))
    paths = sorted(base.rglob('*.smt2'))
    bv = [p for p in paths if p.parent.name == 'bv']
    lia = [p for p in paths if p.parent.name == 'lia']
    assert len(bv) == len(lia) == 254
    manifest('bv', bv, dict(paired_lia=254, encoding='native unsigned bit-vector maximization'))
    manifest('bv_lia', lia, dict(paired_bv=254, encoding='original integer encoding'))


def prepare_maxsmt():
    base = EXTRACTED / 'maxsmt'
    base.mkdir(parents=True, exist_ok=True)
    unrar = ROOT / 'tools/full-campaign-deps/installed/usr/bin/unrar-nonfree'
    if not unrar.exists():
        unrar = ROOT / 'tools/full-campaign-deps/installed/usr/bin/unrar'
    subprocess.run([str(unrar), 'x', '-o-', '-idq', str(DATA/'downloads/PairLS.rar'), str(base)+'/'], check=True)
    paths = sorted((base/'PairLS/MAXSMT-LIA/z3_format').rglob('*.smt2'))
    assert len(paths) == 2264
    manifest('maxsmt', paths, dict(
        source='Entire published PairLS release; 283 base inputs times 4 ratios times 2 weight regimes',
        paper_population_not_equal_to_release=True,
        missing_from_release='IDL, LL and the bofill LIA family are not contained in this release.',
        paired_local_search_format='Retained separately; not double-counted as new instances.'))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('suite', choices=['fp', 'bv', 'maxsmt'])
    args = ap.parse_args()
    {'fp': prepare_fp, 'bv': prepare_bv, 'maxsmt': prepare_maxsmt}[args.suite]()
