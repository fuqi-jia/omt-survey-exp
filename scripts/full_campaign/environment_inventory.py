#!/usr/bin/env python3
"""Record OS metadata for every host that has completed a campaign run.

Per-run provenance remains authoritative. OS release is a supplementary probe
at the recorded time, not retroactively asserted to be a per-run observation.
No control-plane configuration or environment variables are exported.
"""
import concurrent.futures
import datetime
import json
from pathlib import Path
import shlex
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'runs/full20261009'
sys.path[:0] = ['/pub/data/jiafq/experimentos/src', '/pub/data/jiafq/experimentos/pylibs']

PROBE = r'''
import datetime,json,os,platform
from pathlib import Path
base=Path(RUN_DIR)
provenance=json.loads((base/'evidence/provenance.json').read_text())
actual=json.loads((base/'h_actual.json').read_text())
release={}
for line in Path('/etc/os-release').read_text().splitlines():
 if '=' in line:
  k,v=line.split('=',1)
  if k in ['ID','VERSION_ID','PRETTY_NAME']:release[k]=v.strip('"')
print(json.dumps(dict(observed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 os_release=release,current_kernel=platform.release(),
 source_run=base.name,
 run_provenance={k:provenance[k] for k in ['hostname','platform','python','cpu','z3','z3_binary_sha256','oms_sha256','script_sha256','memory_bytes','budget_s']},
 platform_run={k:actual.get(k) for k in ['hostname','kernel','started_at','eos_cpu_ids','cpus_allowed_list']})))
'''


def main():
    from eos.config import load_config
    from eos.api.app import _build_executors
    executors = _build_executors(load_config('/pub/data/jiafq/experimentos/config.toml'))
    con = sqlite3.connect('file:/pub/data/jiafq/eos/eos.db?mode=ro', uri=True)
    hosts = {}
    for host, workdir in con.execute("select r.host,r.workdir from run r join experiment e on r.experiment_id=e.id "
                                    "where e.name like 'jos-full-%-20261009-r1' and r.status='success' order by r.ended_at"):
        hosts.setdefault(host, workdir)
    con.close()

    def probe(item):
        host, workdir = item
        code = 'RUN_DIR=' + repr(workdir) + '\n' + PROBE
        result = executors[host].run('python3 -c ' + shlex.quote(code), timeout=60)
        if result.exit_code:
            raise RuntimeError(host + ': environment probe failed: ' + result.stderr[-500:])
        return dict(host=host, **json.loads(result.stdout))

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(probe, sorted(hosts.items())))
    report = dict(observed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  scope='Every host with a successful campaign run; supplementary OS probe plus archived run provenance',
                  hosts=records)
    (OUT / 'environment-inventory.json').write_text(json.dumps(report, indent=2) + '\n')
    for row in records:
        print(row['host'], row['os_release']['PRETTY_NAME'], row['run_provenance']['cpu'], flush=True)


if __name__ == '__main__':
    main()
