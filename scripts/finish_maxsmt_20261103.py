#!/usr/bin/env python3
"""Supervise the complete CGM run and update its reserved manuscript block."""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

import maxsmt_public_20261103 as experiment

ROOT = experiment.ROOT
RUN = experiment.RUN
MANUSCRIPT = ROOT.parent / "gomt"
SURVEY = MANUSCRIPT / "omt-survey"
SECTION = SURVEY / "sections/exp-evaluation.tex"
BEGIN = "% MAXSMT_RESULTS_BEGIN"
END = "% MAXSMT_RESULTS_END"


def write_status(**values):
    values["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    experiment.save(RUN / "automatic_update.json", values)
    print(json.dumps(values, ensure_ascii=False), flush=True)


def live_runner():
    for row in subprocess.check_output(["ps", "-eo", "pid,args"], text=True).splitlines():
        parts = row.strip().split(None, 1)
        if len(parts) == 2:
            words = parts[1].split()
            if (len(words) >= 3 and Path(words[0]).name.startswith("python")
                    and Path(words[-2]).name == "maxsmt_public_20261103.py" and words[-1] == "run"):
                try:
                    if Path(f"/proc/{parts[0]}/cwd").samefile(ROOT):
                        return int(parts[0])
                except OSError:
                    pass
    return None


def stop_solvers():
    for row in subprocess.check_output(["ps", "-eo", "pid,args"], text=True).splitlines():
        parts = row.strip().split(None, 1)
        if len(parts) != 2 or str(RUN / "inputs") not in parts[1]:
            continue
        if parts[1].startswith((str(experiment.Z3), str(experiment.OMS))):
            try:
                os.killpg(int(parts[0]), signal.SIGTERM)
            except ProcessLookupError:
                pass


def preserve_interrupted():
    target_root = RUN / "interrupted_calls" / time.strftime("restart-%Y%m%d-%H%M%S")
    for path in (RUN / "results").glob("*/*"):
        if path.is_dir() and not (path / "result.json").exists():
            target = target_root / path.parent.name / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            path.rename(target)


def run_checked(command, cwd):
    environment = dict(os.environ)
    environment["PATH"] = "/tmp/gomt-texlive-fix-njnggqer/bin:" + environment["PATH"]
    subprocess.run(command, cwd=cwd, env=environment, check=True)


def finalize():
    manifest = json.loads((RUN / "manifest.json").read_text())
    result_paths = sorted((RUN / "results").glob("*/*/result.json"))
    expected = len(manifest["instances"]) * len(manifest["configs"])
    assert len(result_paths) == expected, f"Not ready: {len(result_paths)}/{expected}"
    rows = [json.loads(p.read_text()) for p in result_paths]
    allowed = {"optimal", "unsat", "timeout", "memory"}
    assert all(r["status"] in allowed for r in rows), "Unexpected status requires investigation"
    assert all(r.get("validation", {}).get("feasible") for r in rows if r["status"] == "optimal")
    expected_keys = {(c["id"], s) for c in manifest["instances"] for s in manifest["configs"]}
    assert {(r["instance"], r["config"]) for r in rows} == expected_keys
    for row in rows:
        source = RUN / "inputs" / row["instance"] / (row["config"] + ".smt2")
        assert hashlib.sha256(source.read_bytes()).hexdigest() == row["input_sha256"]
    run_checked([sys.executable, "scripts/maxsmt_public_20261103.py", "table"], ROOT)
    summary = json.loads((RUN / "summary.json").read_text())
    assert not summary["disagreements"]
    total = len(manifest["instances"])
    completed = {c: sum(r["config"] == c and r["status"] in ("optimal", "unsat") for r in rows)
                 for c in manifest["configs"]}
    if all(n == total for n in completed.values()):
        prose = f"表~\\ref{{tab:exp-maxsmt}} 中, 四种配置均完成全部 ${total}$ 个实例."
    else:
        a, b, c, d = [completed[name] for name in manifest["configs"]]
        prose = (f"表~\\ref{{tab:exp-maxsmt}} 中, $\\nu Z$ 的 MaxRes、WMax 配置分别完成 "
                 f"${a}/{total}$、${b}/{total}$ 个实例, OptiMathSAT 的 OMT、MaxRes 配置分别完成 "
                 f"${c}/{total}$、${d}/{total}$ 个实例.")
    payload = ("\n\\paragraph{公开 MaxSMT 基准.}\n\\label{par:exp-maxsmt}\n"
               + prose + "\n\n" + (RUN / "table.tex").read_text() + "\n")
    source = SECTION.read_text()
    assert source.count(BEGIN) == source.count(END) == 1
    before, rest = source.split(BEGIN)
    current, after = rest.split(END)
    assert not current.strip() or current == payload, "Reserved block was edited; preserve author changes"
    updated = before + BEGIN + payload + END + after
    if any(n != total for n in completed.values()):
        old = "证明词典序最优或判定硬约束不可满足计为完成."
        new = "证明词典序最优或判定硬约束不可满足计为完成, 表~\\ref{tab:exp-maxsmt} 的上标按完成数统计."
        assert updated.count(old) == 1 or new in updated
        updated = updated.replace(old, new)
    # Touch only the reserved MaxSMT block and its metric sentence.
    backup = RUN / "manuscript-before-results.tex"
    if not backup.exists():
        backup.write_text(source)
    temp = SECTION.with_suffix(".tex.tmp")
    temp.write_text(updated)
    temp.replace(SECTION)
    stats = "revision/citations-20261028/figure2-statistics/"
    for name in ("extract_cited_literature.py", "generate_figures.py", "extract_cited_literature.py"):
        run_checked([sys.executable, stats + name], MANUSCRIPT)
    run_checked(["./build.sh"], SURVEY)
    run_checked([sys.executable, "revision/abstract-20261008/check_freeze.py"], MANUSCRIPT)
    run_checked([sys.executable, "revision/citations-20261028/check_delivery.py"], MANUSCRIPT)
    run_checked(["git", "-c", "core.whitespace=cr-at-eol", "diff", "--check"], MANUSCRIPT)
    run_checked(["git", "-c", "core.whitespace=cr-at-eol", "diff", "--check"], ROOT)
    import fitz
    pdf = SURVEY / "main.pdf"
    document = fitz.open(pdf)
    aux = (SURVEY / "main.aux").read_text()
    def page_of(label):
        match = re.search(r"\\newlabel\{" + re.escape(label) + r"\}\{\{[^}]*\}\{(\d+)\}", aux)
        assert match, label
        return int(match[1])
    paragraph_page, table_page = page_of("par:exp-maxsmt"), page_of("tab:exp-maxsmt")
    assert abs(paragraph_page - table_page) <= 1, "MaxSMT table drifted from its discussion"
    previews = RUN / "preview"
    previews.mkdir(exist_ok=True)
    for number in sorted({paragraph_page, table_page}):
        page = document[number - 1]
        assert "\ufffd" not in page.get_text()
        page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False).save(previews / f"page-{number}.png")
    validation = json.loads((MANUSCRIPT / "revision/citations-20261028/validation.json").read_text())
    write_status(status="complete", completed=expected, expected=expected,
                 completed_by_config=completed, pages=len(document), paragraph_page=paragraph_page,
                 table_page=table_page, pdf=str(pdf), pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
                 abstract_freeze="pass", build_messages=validation["build_messages"],
                 preview_directory=str(previews))


def supervise():
    os.sched_setaffinity(0, {12, 14})
    manifest = json.loads((RUN / "manifest.json").read_text())
    expected = len(manifest["instances"]) * len(manifest["configs"])
    cache, restarts = {}, 0
    while True:
        if (RUN / "CANCEL_AUTOMATIC_UPDATE").exists():
            pid = live_runner()
            if pid:
                os.kill(pid, signal.SIGTERM)
            stop_solvers()
            write_status(status="cancelled", completed=len(cache), expected=expected)
            return
        for cell in manifest["instances"]:
            for config in manifest["configs"]:
                key = (cell["id"], config)
                if key in cache:
                    continue
                path = RUN / "results" / cell["id"] / config / "result.json"
                if path.exists():
                    cache[key] = json.loads(path.read_text())
        states = dict(collections.Counter(r["status"] for r in cache.values()))
        pid = live_runner()
        write_status(status="running" if pid else "waiting", completed=len(cache), expected=expected,
                     statuses=states, runner_pid=pid, restarts=restarts)
        if len(cache) == expected and pid is None:
            finalize()
            return
        if pid is None and len(cache) < expected:
            assert restarts < 3, "Runner stopped repeatedly; investigation required"
            stop_solvers()
            preserve_interrupted()
            log = (RUN / f"supervised-run-{restarts}.log").open("a")
            subprocess.Popen(["python3", "-u", "scripts/maxsmt_public_20261103.py", "run"],
                             cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, start_new_session=True)
            log.close()
            restarts += 1
        time.sleep(30)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("supervise", "finalize"))
    arguments = parser.parse_args()
    try:
        {"supervise": supervise, "finalize": finalize}[arguments.action]()
    except Exception as error:
        write_status(status="needs_review", error=str(error))
        raise
