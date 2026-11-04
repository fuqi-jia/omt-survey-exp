#!/usr/bin/env python3
"""Reproduce the predeclared cohort from the archived MINLPLib metadata."""

import csv
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "benchmarks/minlplib-qcqp-20261102"


def main():
    manifest = json.loads((DEST / "selection.json").read_text())
    metadata = DEST / "instancedata.csv"
    assert hashlib.sha256(metadata.read_bytes()).hexdigest() == manifest["metadata_sha256"]
    with metadata.open() as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    selected = [r for r in rows if r["convex"] == "False" and r["nbinvars"] == "0"
                and r["nintvars"] == "0" and 2 <= int(r["nvars"]) <= 5
                and int(r["ncons"]) <= 10 and r["probtype"] in ("QP", "QCP", "QCQP")
                and float(r["gap"]) <= 1e-6 and "osil" in r["formats"]]
    assert [r["name"] for r in selected] == [r["name"] for r in manifest["selected"]]
    for r in manifest["selected"]:
        path = DEST / (r["name"] + ".osil")
        if not path.exists():
            path.write_bytes(urllib.request.urlopen(r["source_url"], timeout=60).read())
        assert hashlib.sha256(path.read_bytes()).hexdigest() == r["sha256"]
    print(f"PASS: all {len(selected)} eligible instances, complete selection and source hashes")


if __name__ == "__main__":
    main()
