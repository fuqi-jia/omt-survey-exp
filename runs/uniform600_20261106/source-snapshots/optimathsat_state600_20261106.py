#!/usr/bin/env python3
"""Repeat the two native OptiMathSAT status observations under the new cap."""
from pathlib import Path
import hashlib
import json
import os
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get('OMT_UNIFORM600_OUTPUT', 'runs/uniform600_20261106') / 'diagnostics'


def main():
    from memory_limit import limit_memory
    limit_memory(4)
    os.sched_setaffinity(0, {0})
    sys.path[:0] = ['/tmp/gomt-optimathsat-api-20261103/lib',
                    str(ROOT / 'tools/optimathsat-1.7.4-linux-64-bit/python')]
    import _optimathsat
    sys.modules.setdefault('_mathsat', _optimathsat)
    import optimathsat as ms
    import review_diagnostics_20261104 as source
    original_solve = ms.msat_solve
    def solve(env):
        begun = time.monotonic()
        callback = lambda: int(time.monotonic() - begun >= 600)
        assert ms.msat_set_termination_test(env, callback) == 0
        return original_solve(env)
    ms.msat_solve = solve
    source.OUT = OUT
    source.optimathsat()
    for path in (OUT / 'optimathsat').glob('*.json'):
        row = json.loads(path.read_text())
        row['timeout_s'] = 600
        path.write_text(json.dumps(row, indent=2) + '\n')
    OUT.mkdir(parents=True, exist_ok=True)
    source.save(OUT / 'environment.json', dict(python=sys.version, timeout_s=600,
        solver='OptiMathSAT 1.7.4', memory_gb=4, threads=1,
        api_module_sha256=hashlib.sha256(Path(_optimathsat.__file__).read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest(),
        auxiliary_calls=2, execution='local'))


if __name__ == '__main__':
    main()
