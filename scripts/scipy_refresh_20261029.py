#!/usr/bin/env python3
"""Run the eight SLSQP comparisons under a shared 120-second process cap."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='runs/nra_20261029')
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    out = ROOT / args.output
    out.mkdir(parents=True, exist_ok=True)
    if args.worker:
        import nra_refresh_20261028 as nra
        nra.OUT = out
        nra.scipy_results()
        return
    command = [sys.executable, __file__, '--worker', '--output', args.output]
    started = time.monotonic()
    proc = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout)
    (out / 'scipy120.stdout').write_text(proc.stdout)
    (out / 'scipy120.stderr').write_text(proc.stderr)
    receipt = dict(command=command, timeout_s=args.timeout,
                   wall_s=time.monotonic() - started, returncode=proc.returncode,
                   script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out / 'scipy-process.json').write_text(json.dumps(receipt, indent=2) + '\n')
    proc.check_returncode()


if __name__ == '__main__':
    main()
