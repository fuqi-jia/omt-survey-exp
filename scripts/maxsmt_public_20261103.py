#!/usr/bin/env python3
"""Published CGM MaxSMT inputs, native engines, and exact witness checks."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import resource
import signal
import statistics
import subprocess
import sys
import time
import zipfile

import _bootstrap  # noqa: F401
from nra_public_20261102 import load_z3, sexprs

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/maxsmt_cgm_20261103"
ARCHIVE = ROOT / "tools/maxsmt-20261103/CGM-Experiment-full.zip"
Z3 = Path("/tmp/gomt-z3-5.3.3/bin/z3")
OMS = ROOT / "tools/optimathsat-1.7.4-linux-64-bit/bin/optimathsat"
CONFIGS = ("z3-maxres", "z3-wmax", "oms-omt", "oms-maxres")
SCALES = (2, 11, 21)
PREFERENCES = (6, 8, 12)
LIMIT = 600
CORES = (0, 2, 4, 6, 8, 10)


class EmptyInput(ValueError):
    pass


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def smt(node):
    return "(" + " ".join(map(smt, node)) + ")" if isinstance(node, list) else node


def parse(source):
    # CGM's artifact has no strings or quoted symbols containing semicolons.
    assert not re.search(r'["|]', source)
    commands = sexprs(re.sub(r";[^\n]*", "", source))
    declarations, hard, groups, objectives = [], [], {}, []
    for command in commands:
        assert isinstance(command, list) and command
        head = command[0]
        if head == "declare-fun":
            assert command[2] == [] and command[3] in ("Bool", "Int", "Real")
            declarations.append(command)
        elif head == "assert":
            hard.append(command)
        elif head == "assert-soft":
            options = dict(zip(command[2::2], command[3::2]))
            assert set(options) <= {":weight", ":id"}
            weight = int(options.get(":weight", "1"))
            # Auxiliary signed weights express numeric attributes in CGM.
            groups.setdefault(options[":id"], []).append((command[1], weight))
        elif head == "minimize":
            assert len(command) == 2
            objectives.append(command[1])
        else:
            assert head.startswith("set-option") or head in (
                "check-sat", "set-model", "get-model", "exit")
    assert objectives == ["unsat_preferences", "unsat_requirements", "sat_tasks"]
    if not declarations and not hard and not groups:
        raise EmptyInput("Published placeholder has no declarations, constraints, or soft objectives")
    assert all(w > 0 for g in objectives for _, w in groups[g])
    return declarations, hard, groups, objectives


def cost(clauses):
    return ["+", "0"] + [["ite", clause, "0", str(w) if w >= 0 else ["-", str(-w)]]
                     for clause, w in clauses]


def encode(source, config, parsed=None):
    declarations, hard, groups, objectives = parsed if parsed is not None else parse(source)
    base = ["(set-option :produce-models true)"]
    base += ["(set-logic QF_LIRA)"]
    base += list(map(smt, declarations))
    base += [smt(["define-fun", group, [], "Int", cost(clauses)])
             for group, clauses in groups.items() if group not in objectives]
    base += list(map(smt, hard))
    costs = [f"__cgm_cost_{i}" for i in range(len(objectives))]
    base += [smt(["define-fun", name, [], "Int", cost(groups[group])])
             for name, group in zip(costs, objectives)]
    hard_source = "\n".join(base) + "\n"
    if config.startswith("oms"):
        # CGM's auxiliary assert-soft IDs define PB terms used by hard constraints.
        # OptiMathSAT supports them natively without creating extra objectives.
        # Keep the original command order and native PB encoding for this solver.
        commands = sexprs(re.sub(r";[^\n]*", "", source))
        native = ["(set-option :produce-models true)"]
        native += [smt(c) for c in commands
                   if c[0] in ("declare-fun", "assert", "assert-soft", "minimize")]
        native += ["(check-sat)", "(get-objectives)", "(load-objective-model 2)",
                   "(get-value (" + " ".join([d[1] for d in declarations] + objectives) + "))",
                   "(exit)"]
        return "\n".join(native) + "\n", hard_source, [d[1] for d in declarations], costs
    if config.startswith("z3"):
        base.append("(set-option :opt.priority lex)")
        base.append(f"(set-option :opt.maxsat_engine {config.split('-')[1]})")
    for group in objectives:
        base += [smt(["assert-soft", clause, ":weight", str(w), ":id", group])
                 for clause, w in groups[group]]
        if config.startswith("oms"):
            base.append(smt(["minimize", group]))
    base += ["(check-sat)", "(get-objectives)"]
    if config.startswith("oms"):
        base.append("(load-objective-model 2)")
    variables = [command[1] for command in declarations]
    base += ["(get-value (" + " ".join(variables + costs) + "))", "(exit)"]
    return "\n".join(base) + "\n", hard_source, variables, costs


def prepare():
    assert ARCHIVE.exists()
    import io
    with zipfile.ZipFile(ARCHIVE) as outer:
        with zipfile.ZipFile(io.BytesIO(outer.read("exp2.zip"))) as inner:
            selected = []
            for name in inner.namelist():
                m = re.fullmatch(r"exp2/2N(6|8|12)P/Experiment_(\d+)/(\d+)\.smt2", name)
                if m and int(m[2]) in SCALES:
                    selected.append((int(m[2]), int(m[1]), int(m[3]), name))
            assert len(selected) == len(SCALES) * 400, len(selected)
            for n in SCALES:
                for p in PREFERENCES:
                    expected = 200 if p == 8 else 100
                    assert sorted(i for nn, pp, i, _ in selected if nn == n and pp == p) == list(range(1, expected + 1))
            cells, excluded = [], []
            for n, p, seed, name in sorted(selected):
                instance = f"cgm-n{n:03}-p{p:02}-i{seed:03}"
                original = inner.read(name)
                path = RUN / "inputs" / instance
                path.mkdir(parents=True, exist_ok=True)
                try:
                    parsed = parse(original.decode())
                except EmptyInput as exc:
                    rejected = RUN / "excluded_inputs" / instance / "original.smt2"
                    rejected.parent.mkdir(parents=True, exist_ok=True)
                    rejected.write_bytes(original)
                    excluded.append(dict(id=instance, archive_member=name,
                                         source_sha256=digest(original), reason=str(exc)))
                    continue
                declarations, hard_constraints, groups, objectives = parsed
                if not all((path / f"{c}.smt2").exists() for c in CONFIGS) or not (path / "hard.smt2").exists():
                    (path / "original.smt2").write_bytes(original)
                    for config in CONFIGS:
                        encoded, hard_source, _, _ = encode(original.decode(), config, parsed)
                        (path / f"{config}.smt2").write_text(encoded)
                    (path / "hard.smt2").write_text(hard_source)
                else:
                    assert (path / "original.smt2").read_bytes() == original
                cells.append(dict(id=instance, replicas=n, preferences_per_replica=p,
                                  original_index=seed, archive_member=name,
                                  source_sha256=digest(original), variables=len(declarations),
                                  hard_constraints=len(hard_constraints),
                                  objective_soft_counts=[len(groups[g]) for g in objectives]))
    manifest = dict(dataset="CGM-Tool published experiment 2, PRT objectives",
                    paper_doi="10.1007/s00766-016-0263-5",
                    source_url="http://www.cgm-tool.eu/download/Experiment_SMT_Files.zip",
                    archive_sha256=digest(ARCHIVE.read_bytes()),
                    selection=dict(replicas=SCALES, preferences_per_replica=PREFERENCES,
                                   indices="all 1..100 for p=6,12; all 1..200 for p=8, as released"),
                    configs=CONFIGS, timeout_s=LIMIT, memory_bytes=4 * 1024**3,
                    cores=CORES, candidate_files=len(selected), excluded=excluded, instances=cells,
                    normalization="Preserve original three lexicographic soft objectives in PRT order. "
                    "Non-objective assert-soft groups encode numeric attributes; expand these into "
                    "ite sums for Z3, without introducing extra Z3 objectives. OptiMathSAT retains "
                    "all original native PB groups and command order. "
                    "Preserve every original hard constraint and signed auxiliary weight.",
                    binaries={str(p): digest(p.read_bytes()) for p in (Z3, OMS)})
    save(RUN / "manifest.json", manifest)
    print("prepared", len(cells), "instances", len(cells) * len(CONFIGS), "calls", flush=True)


def limits(core):
    os.setsid()
    os.sched_setaffinity(0, {core})
    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))


def validate(instance, config, stdout):
    declarations, _, _, _ = parse((RUN / "inputs" / instance / "original.smt2").read_text())
    query_costs = (["unsat_preferences", "unsat_requirements", "sat_tasks"]
                   if config.startswith("oms") else [f"__cgm_cost_{i}" for i in range(3)])
    names = [d[1] for d in declarations] + query_costs
    values = None
    for node in reversed(sexprs(stdout)):
        if isinstance(node, list) and len(node) == len(names):
            if all(isinstance(pair, list) and len(pair) == 2 and isinstance(pair[0], str)
                   for pair in node):
                candidate = dict(node)
                if set(candidate) == set(names):
                    values = candidate
                    break
    assert values is not None, "missing complete model values"
    assignments = "\n".join(smt(["assert", ["=", name, values[name]]]) for name in names[:-3])
    assignments += "\n" + "\n".join(smt(["assert", ["=", f"__cgm_cost_{i}", values[name]]])
                                      for i, name in enumerate(query_costs))
    z3 = load_z3()
    context = z3.Context()
    solver = z3.Solver(ctx=context)
    solver.set(timeout=30000)
    solver.from_string((RUN / "inputs" / instance / "hard.smt2").read_text() + assignments)
    status = str(solver.check())
    assert status == "sat", "invalid model or recomputed costs: " + status
    objective = []
    for name in names[-3:]:
        value = values[name]
        assert isinstance(value, str) and value.isdigit()
        objective.append(int(value))
    return dict(feasible=True, recomputed_costs=objective, check=status)


def run_cell(cell, config, core, timeout=LIMIT):
    instance = cell["id"]
    out = RUN / "results" / instance / config
    result_path = out / "result.json"
    source = RUN / "inputs" / instance / f"{config}.smt2"
    if result_path.exists():
        previous = json.loads(result_path.read_text())
        assert previous["input_sha256"] == digest(source.read_bytes())
        return previous
    out.mkdir(parents=True, exist_ok=True)
    command = ([str(Z3), f"-T:{timeout}", str(source)] if config.startswith("z3")
               else [str(OMS), "-optimization=TRUE", "-opt.priority=lex",
                     "-opt.maxsmt_engine=" + config.split("-")[1],
                     "-unsat_core_generation=" + ("1" if config == "oms-maxres" else "0"),
                     str(source)])
    environment = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    begin = time.perf_counter()
    timed_out = False
    with (out / "stdout.txt").open("w") as stdout, (out / "stderr.txt").open("w") as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=environment,
                                   preexec_fn=lambda: limits(core))
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    elapsed = time.perf_counter() - begin
    stdout, stderr = (out / "stdout.txt").read_text(), (out / "stderr.txt").read_text()
    result = dict(instance=instance, config=config, command=command, core=core,
                  input_sha256=digest(source.read_bytes()), elapsed_s=elapsed,
                  returncode=process.returncode, timeout_s=timeout)
    if timed_out or re.search(r"\btimeout\b", stdout, re.I):
        result["status"] = "timeout"
    elif "out of memory" in (stdout + stderr).lower():
        result["status"] = "memory"
    elif re.search(r"^unsat\s*$", stdout, re.M) and "(error" not in stdout.split("unsat", 1)[0]:
        result["status"] = "unsat"
    elif process.returncode != 0 or "(error" in stdout or re.search(r"^unknown\s*$", stdout, re.M):
        result["status"] = "error"
    elif re.search(r"^sat\s*$", stdout, re.M) and "partial search" not in stdout.lower():
        try:
            result["validation"] = validate(instance, config, stdout)
            result["objective"] = result["validation"]["recomputed_costs"]
            result["status"] = "optimal"
        except Exception as exc:
            result.update(status="invalid", validation_error=str(exc))
    else:
        result["status"] = "error"
    save(result_path, result)
    return result


def run():
    # Reserve two physical cores for input handling and witness validation.
    os.sched_setaffinity(0, {12, 14})
    manifest = json.loads((RUN / "manifest.json").read_text())
    jobs = [(c, s) for c in manifest["instances"] for s in CONFIGS]
    pending = queue.Queue()
    for job in jobs:
        pending.put(job)
    def work(index):
        while True:
            try:
                cell, config = pending.get_nowait()
            except queue.Empty:
                break
            r = run_cell(cell, config, CORES[index])
            print(cell["id"], config, r["status"], round(r["elapsed_s"], 3), flush=True)
    with concurrent.futures.ThreadPoolExecutor(len(CORES)) as pool:
        list(pool.map(work, range(len(CORES))))
    summarize()


def summarize():
    manifest = json.loads((RUN / "manifest.json").read_text())
    rows = []
    for path in sorted((RUN / "results").glob("*/*/result.json")):
        row = json.loads(path.read_text())
        if row["status"] == "error":
            stdout = (path.parent / "stdout.txt").read_text()
            if re.search(r"^unsat\s*$", stdout, re.M) and "(error" not in stdout.split("unsat", 1)[0]:
                row["status"] = "unsat"
                row["classification_note"] = "Hard UNSAT is conclusive; trailing model queries have no model."
                save(path, row)
        rows.append(row)
    disagreement = []
    for cell in manifest["instances"]:
        completed = [r for r in rows if r["instance"] == cell["id"]]
        costs = {tuple(r["objective"]) for r in completed if r["status"] == "optimal"}
        states = {r["status"] for r in completed}
        if len(costs) > 1 or ("unsat" in states and "optimal" in states):
            disagreement.append(cell["id"])
    table = []
    for n in SCALES:
        for p in PREFERENCES:
            ids = {c["id"] for c in manifest["instances"]
                   if c["replicas"] == n and c["preferences_per_replica"] == p}
            row = dict(replicas=n, preferences_per_replica=p, instances=len(ids), configs={})
            for config in CONFIGS:
                selected = [r for r in rows if r["instance"] in ids and r["config"] == config]
                times = [r["elapsed_s"] if r["status"] in ("optimal", "unsat") else float("inf")
                         for r in selected]
                median = statistics.median(times) if times else float("inf")
                row["configs"][config] = dict(completed=len(selected),
                    optimal=sum(r["status"] == "optimal" for r in selected),
                    unsat=sum(r["status"] == "unsat" for r in selected),
                    median_s=median if median != float("inf") else None,
                    statuses={s: sum(r["status"] == s for r in selected)
                              for s in sorted({r["status"] for r in selected})})
            table.append(row)
    save(RUN / "summary.json", dict(expected_calls=len(manifest["instances"]) * len(CONFIGS),
         completed_calls=len(rows), disagreements=disagreement, table=table))
    print("summary", len(rows), "calls; disagreements", disagreement, flush=True)


def table():
    summarize()
    summary = json.loads((RUN / "summary.json").read_text())
    assert summary["completed_calls"] == summary["expected_calls"]
    assert not summary["disagreements"]
    lines = [r"\begin{table}[!htbp]", r"\centering",
             r"\caption{CGM MaxSMT 基准的求解时间 (秒)}",
             r"\label{tab:exp-maxsmt}", r"\small", r"\setlength{\tabcolsep}{3pt}",
             r"\begin{tabular}{@{}rrr rrrr@{}}", r"\toprule",
             r"& & & \multicolumn{2}{c}{$\nu Z$} & \multicolumn{2}{c}{OptiMathSAT} \\",
             r"\cmidrule(lr){4-5}\cmidrule(lr){6-7}",
             r"$N$ & $p$ & 实例数 & MaxRes & WMax & OMT & MaxRes \\",
             r"\midrule"]
    last_n = None
    for row in summary["table"]:
        if last_n is not None and row["replicas"] != last_n:
            lines.append(r"\midrule")
        last_n = row["replicas"]
        cells = [str(row[k]) for k in ("replicas", "preferences_per_replica", "instances")]
        for config in CONFIGS:
            value = row["configs"][config]
            assert value["completed"] == row["instances"]
            median = "T/O" if value["median_s"] is None else f"{value['median_s']:.2f}"
            completed = value["optimal"] + value["unsat"]
            if completed != row["instances"]:
                median += f"$^{{{completed}/{row['instances']}}}$"
            cells.append(median)
        lines.append(" & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    (RUN / "table.tex").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "run", "summarize", "table"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run, "summarize": summarize, "table": table}[args.action]()
