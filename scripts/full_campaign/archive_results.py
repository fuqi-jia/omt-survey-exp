#!/usr/bin/env python3
"""Collect complete raw evidence after a suite terminates; preserve source hosts.

Run with the ExperimentOS control node's Python 3.14. No credentials are copied
or printed. Archives contain only this experiment's result files, not datasets,
executables, platform configuration, or other users' jobs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import sqlite3
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'runs/full20261009'
sys.path[:0] = ['/pub/data/jiafq/experimentos/src', '/pub/data/jiafq/experimentos/pylibs']

PACKER = r'''
import hashlib,io,json,tarfile
from pathlib import Path
config=json.loads(Path(CONFIG_PATH).read_text())
target=Path(config['target']);target.parent.mkdir(parents=True,exist_ok=True)
temporary=target.with_suffix('.partial')
index=[]
with tarfile.open(temporary,'w:gz',compresslevel=3) as archive:
 for row in config['runs']:
  base=Path(row['workdir'])
  assert base.name==row['id'] and base.parent.name==config['experiment_name']
  paths=[p for p in (base/'evidence').rglob('*') if p.is_file()]
  assert (base/'evidence/provenance.json') in paths,base
  for name in ['metrics.json','h_actual.json','run.log','exit_code']:
   p=base/name
   if p.exists():paths.append(p)
  assert base/'metrics.json' in paths,base
  for p in sorted(paths):
   assert not p.is_symlink(),p
   digest=hashlib.sha256(p.read_bytes()).hexdigest()
   member=row['id']+'/'+p.relative_to(base).as_posix()
   archive.add(p,arcname=member,recursive=False)
   index.append(dict(run=row['id'],member=member,bytes=p.stat().st_size,sha256=digest))
 body=json.dumps(dict(experiment=config['experiment_name'],host=config['host'],files=index),indent=2).encode()
 info=tarfile.TarInfo('archive-index.json');info.size=len(body)
 archive.addfile(info,io.BytesIO(body))
temporary.replace(target)
print(json.dumps(dict(path=str(target),files=len(index),runs=len(config['runs']),bytes=target.stat().st_size)))
'''


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify(archive_path, expected_runs):
    from status_reviews import check_evidence
    reviews_path = OUT / 'status-reviews.json'
    reviews = json.loads(reviews_path.read_text()) if reviews_path.exists() else {}
    runtime = {
        'parser_source_sha256': sha(ROOT / 'scripts/revision_public_fp.py'),
        'z3_binary_sha256': sha(ROOT / 'tools/full-python/z3/lib/libz3.so'),
        'oms_sha256': sha(ROOT / 'tools/optimathsat-1.7.4-linux-64-bit/bin/optimathsat'),
    }
    with tarfile.open(archive_path) as archive:
        index = json.load(archive.extractfile('archive-index.json'))
        assert {r['run'] for r in index['files']} == set(expected_runs)
        assert len({r['member'] for r in index['files']}) == len(index['files'])
        for row in index['files']:
            content = archive.extractfile(row['member']).read()
            assert len(content) == row['bytes']
            assert hashlib.sha256(content).hexdigest() == row['sha256']
        for run_id, expected in expected_runs.items():
            provenance = json.load(archive.extractfile(run_id + '/evidence/provenance.json'))
            assert provenance['input']['id'] == expected['case_id']
            assert provenance['input']['sha256'] == expected['source_sha256']
            assert all(provenance[key] == digest for key, digest in runtime.items())
            diagnostic = provenance['input']['suite'] == 'bv_lia'
            harness = 'run_lia_diagnostic.py' if diagnostic else 'run_case.py'
            assert provenance['script_sha256'] == sha(ROOT / 'scripts/full_campaign' / harness)
            if diagnostic:
                assert provenance['common_source_sha256'] == sha(ROOT / 'scripts/full_campaign/run_case.py')
            assert provenance['budget_s'] == 600 and provenance['verification_query_budget_s'] == (0 if diagnostic else 60)
            assert provenance['memory_bytes'] == 8 * 1024**3
            review = reviews.get(run_id + ':oms_lia')
            if review:
                metrics = json.load(archive.extractfile(run_id + '/metrics.json'))
                def raw(name):
                    return archive.extractfile(run_id + '/evidence/' + name).read()
                check_evidence(review, metrics, provenance,
                               raw('oms_lia.native.stdout'), raw('oms_lia.native.stderr'),
                               raw('oms_lia.solve.stderr'))
    return dict(path=archive_path.relative_to(ROOT).as_posix(), sha256=sha(archive_path),
                bytes=archive_path.stat().st_size, runs=len(expected_runs), files=len(index['files']))


def main():
    from eos.config import load_config
    from eos.api.app import _build_executors
    ap = argparse.ArgumentParser()
    ap.add_argument('suite', choices=['fp', 'bv', 'bv_lia', 'maxsmt'])
    args = ap.parse_args()
    name = 'jos-full-' + args.suite + '-20261009-r1'
    con = sqlite3.connect('file:/pub/data/jiafq/eos/eos.db?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    exp = con.execute('select * from experiment where name=?', (name,)).fetchone()
    assert exp is not None
    runs = [dict(r) for r in con.execute('select * from run where experiment_id=?', (exp['id'],))]
    assert runs and all(r['status'] not in {'pending', 'assigned', 'running'} for r in runs), 'Suite still running'
    assert all(r['workdir'] and r['metrics_json'] for r in runs), 'Investigate incomplete infrastructure attempts first'
    by_host = {}
    for run in runs:
        by_host.setdefault(run['host'], []).append(run)
    executors = _build_executors(load_config('/pub/data/jiafq/experimentos/config.toml'))
    raw = OUT / 'raw'
    raw.mkdir(parents=True, exist_ok=True)
    records = []
    for host, host_runs in sorted(by_host.items()):
        expected = {r['id']: json.loads(r['input_meta_json']) for r in host_runs}
        target = raw / (args.suite + '-' + host + '.tar.gz')
        if target.exists():
            record = verify(target, expected)
        else:
            source = raw / 'staged' / target.name
            config = dict(target=str(source), experiment_name=name, host=host,
                          runs=[dict(id=r['id'], workdir=r['workdir']) for r in host_runs])
            config_path = raw / (args.suite + '-' + host + '-archive-request.json')
            config_path.write_text(json.dumps(config, indent=2) + '\n')
            remote_config = '/tmp/jos-' + args.suite + '-' + host + '-archive.json'
            executor = executors[host]
            executor.put(config_path, remote_config)
            code = 'CONFIG_PATH=' + repr(remote_config) + '\n' + PACKER
            command = 'python3 - <<\'JOS_ARCHIVE_PY\'\n' + code + '\nJOS_ARCHIVE_PY\n'
            result = executor.run(command, timeout=3600)
            if result.exit_code:
                raise RuntimeError(host + ': ' + result.stderr[-2000:])
            print(result.stdout, flush=True)
            partial = target.with_suffix('.download')
            executor.get(str(source), partial)
            record = verify(partial, expected)
            partial.replace(target)
            record['path'] = target.relative_to(ROOT).as_posix()
        records.append(dict(host=host, **record))
        (OUT / (args.suite + '-archives.json')).write_text(json.dumps(records, indent=2) + '\n')
        print(host, record['runs'], 'runs archived and hashed', flush=True)
    assert sum(r['runs'] for r in records) == len(runs)


if __name__ == '__main__':
    main()
