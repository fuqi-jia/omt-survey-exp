#!/usr/bin/env python3
"""Run the complete CGM matrix in a separate 64-worker server environment."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys

import maxsmt_public_20261103 as experiment

ROOT = Path(__file__).resolve().parents[1]
CORES = (2, 3, 4, 5, 7, 9, 11, 15, 16, 17, 18, 19, 23, 25, 26, 27,
         28, 29, 33, 35, 36, 38, 39, 40, 41, 42, 43, 46, 49, 52, 53, 54, 56,
         57, 58, 59, 60, 62, 63, 68, 82, 87, 89, 90, 91, 100, 109, 111, 112,
         113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127)
VALIDATION_CORES = (12, 14)
Z3_ROOT = ROOT / "tools/z3-5.3.3"

experiment.RUN = ROOT / "runs/maxsmt_cgm_server_20261103"
experiment.Z3 = Z3_ROOT / "python/z3_solver-5.3.3.0.data/data/bin/z3"
experiment.CORES = CORES


def load_z3():
    bindings = str(Z3_ROOT / "python")
    if bindings not in sys.path:
        sys.path.insert(0, bindings)
    import z3
    assert z3.get_version_string() == "5.3.3"
    return z3


experiment.load_z3 = load_z3


def prepare():
    assert len(CORES) == len(set(CORES)) == 64
    assert not set(CORES) & set(VALIDATION_CORES)
    assert all(0 <= core < 128 and core + 128 not in CORES for core in CORES)
    experiment.prepare()
    path = experiment.RUN / "manifest.json"
    manifest = json.loads(path.read_text())
    cpu = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")), "unknown")
    manifest["execution_environment"] = dict(
        hostname=platform.node(), platform=platform.platform(), processor=cpu,
        python=sys.version, workers=len(CORES), validation_cores=VALIDATION_CORES,
        source_driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        base_driver_sha256=hashlib.sha256((ROOT / "scripts/maxsmt_public_20261103.py").read_bytes()).hexdigest())
    experiment.save(path, manifest)


def run():
    assert json.loads((experiment.RUN / "manifest.json").read_text())["cores"] == list(CORES)
    experiment.run()


def status():
    manifest = json.loads((experiment.RUN / "manifest.json").read_text())
    expected = len(manifest["instances"]) * len(manifest["configs"])
    rows = []
    for path in sorted((experiment.RUN / "results").glob("*/*/result.json")):
        rows.append(json.loads(path.read_text()))
    import collections
    print(json.dumps(dict(completed=len(rows), expected=expected,
                          statuses=dict(sorted(collections.Counter(row["status"] for row in rows).items()))),
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "run", "summarize", "table", "status"))
    arguments = parser.parse_args()
    if arguments.action == "prepare":
        prepare()
    elif arguments.action == "run":
        run()
    elif arguments.action == "status":
        status()
    else:
        getattr(experiment, arguments.action)()
