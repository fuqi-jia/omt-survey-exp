#!/usr/bin/env python3
"""Encoding/parameter checks prompted by the author's comparison question.

These diagnostics are separate from the frozen formal comparison. Known-value
SAT/UNSAT queries are not optimization calls and cannot replace their results.
"""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import time

import nra_public_20261102 as common
import nra_disjunctive_20261102 as logical

OUT = common.ROOT / "runs/nra_z3_check_20261102"


def source(model, profile):
    lines = ["(set-option :produce-models true)", "(set-option :pp.decimal true)",
             "(set-option :pp.decimal_precision 20)", "(set-option :opt.optsmt_nlsat true)",
             "(set-logic QF_NRA)"]
    if profile == "canonical_unlimited_supremum":
        lines.insert(0, "(set-option :opt.optsmt_nlsat_supremum_rlimit 0)")
    for i, var in enumerate(model["variables"]):
        lines += [f"(declare-fun x{i} () Real)", f"(assert (>= x{i} {var['lb']}))", f"(assert (<= x{i} {var['ub']}))"]
    total = "(+ " + " ".join(f"(* {u['b']} x{2*i})" for i, u in enumerate(model["units"])) + ")"
    lines.append(f"(assert (>= {total} {model['demand']}))")
    for i, u in enumerate(model["units"]):
        x, z = f"x{2*i}", f"x{2*i+1}"
        lines.append(f"(assert (or (and (= {x} 0) (= {z} 0)) (and (>= {x} {u['l']}) (>= {z} (+ {u['s']} (* {u['a']} {x} {x}))))))")
    cost = "(+ " + " ".join(f"x{2*i+1}" for i in range(model["n"])) + ")"
    if profile in ("at_reference", "better_than_reference"):
        op = "=" if profile == "at_reference" else "<"
        lines += [f"(assert ({op} {cost} {common.smt_number(model['exact_reference']['value'])}))", "(check-sat)"]
    else:
        lines += [f"(minimize {cost})", "(check-sat)", "(get-objectives)",
                  "(get-value (" + " ".join(f"x{i}" for i in range(len(model["variables"]))) + "))"]
    return "\n".join(lines) + "\n"


def main():
    models = [json.loads(p.read_text()) for p in sorted((logical.OUT / "models").glob("*.json"))]
    profiles = ["canonical", "canonical_unlimited_supremum", "at_reference", "better_than_reference"]
    OUT.mkdir(parents=True, exist_ok=True)
    z3 = common.load_z3()
    equivalence = []
    for m in models:
        original = logical.smt_source(m, "z3").split("(declare-fun obj")[0]
        canonical = source(m, "canonical").split("(minimize")[0]
        a, b = z3.parse_smt2_string(original), z3.parse_smt2_string(canonical)
        assert len(a) == len(b)
        # Prove each conjunct separately: the nonlinear branch comparisons
        # then contain two variables, rather than coupling the entire model.
        statuses = []
        for old, new in zip(a, b):
            solver = z3.Solver()
            solver.set(timeout=10000)
            solver.add(z3.Xor(old, new))
            status = str(solver.check())
            assert status == "unsat", (m["name"], status)
            statuses.append(status)
        equivalence.append(dict(instance=m["name"], conjunct_xor=statuses,
                                equivalent=all(s == "unsat" for s in statuses)))
    common.save(OUT / "encoding-equivalence.json", equivalence)
    tasks = queue.Queue()
    for model in models:
        for profile in profiles:
            if not (OUT / profile / model["name"] / "result.json").exists():
                tasks.put((model, profile))
    def group(core):
        while True:
            try:
                model, profile = tasks.get_nowait()
            except queue.Empty:
                return
            folder = OUT / profile / model["name"]
            folder.mkdir(parents=True, exist_ok=True)
            text = source(model, profile)
            path = folder / "input.smt2"
            path.write_text(text)
            limit = 30 if profile in ("at_reference", "better_than_reference") else 120
            cmd = ["taskset", "-c", str(core), "prlimit", "--as=4294967296", common.SOLVERS["z3"], str(path)]
            start = time.monotonic()
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=limit)
                stdout, stderr, status = p.stdout, p.stderr, "RETURNED"
            except subprocess.TimeoutExpired as exc:
                stdout = (exc.stdout or b"").decode(errors="replace")
                stderr = (exc.stderr or b"").decode(errors="replace")
                status = "TIMEOUT"
            elapsed = time.monotonic()-start
            (folder / "stdout.txt").write_text(stdout)
            (folder / "stderr.txt").write_text(stderr)
            x, parse_error = None, None
            if profile in ("canonical", "canonical_unlimited_supremum") and status == "RETURNED":
                try:
                    x = common.parse_vector(stdout, len(model["variables"]))
                except Exception as exc:
                    parse_error = repr(exc)
            record = dict(instance=model["name"], profile=profile, status=status, elapsed_s=elapsed,
                          timeout_s=limit, core=core, x=x, parse_error=parse_error,
                          input_sha256=hashlib.sha256(text.encode()).hexdigest(),
                          answer=stdout.strip().splitlines()[0] if stdout.strip() else None,
                          **logical.assess(model, x, model["reference"]))
            common.save(folder / "result.json", record)
            print(profile, model["name"], status, record["answer"], record["reference_hit"], round(elapsed,3), flush=True)
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(group, [0,2,4,6,8,10,12,14]))
    rows = [json.loads(p.read_text()) for p in OUT.glob("*/*/result.json")]
    common.save(OUT / "results.json", rows)
    common.save(OUT / "protocol.json", dict(z3_version="5.3.3", nlsat_enabled=True,
        models=len(models), profiles=profiles, formal_comparison_modified=False,
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == "__main__":
    main()
