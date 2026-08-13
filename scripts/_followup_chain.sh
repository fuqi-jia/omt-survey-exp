#!/usr/bin/env bash
# Sequential follow-up after the jobshop_seeds run finishes.
# Strictly serial: every step measures wall-clock, so nothing may overlap.
set -u
cd "$(dirname "$0")/.."
PY=.venv-cplex/bin/python
LOG=runs/_followup.log
say(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

# 1) wait for the main run to exit
say "waiting for jobshop_seeds (pid ${MAIN_PID:-none}) to finish..."
while [ -n "${MAIN_PID:-}" ] && kill -0 "$MAIN_PID" 2>/dev/null; do sleep 30; done
say "jobshop_seeds finished"

# 2) drop the two cells that were touched concurrently, then let --resume redo them
say "dropping the 2 concurrency-touched cells and re-running them"
$PY - <<'PY' | tee -a "$LOG"
import json
p = "runs/jobshop_seeds/results.jsonl"
drop = {("B_jobshop_10_6", "scip-bigm"), ("B_jobshop_10_7", "highs-bigm")}
rows = [json.loads(l) for l in open(p)]
keep = [r for r in rows if (r["name"], r["solver"]) not in drop]
with open(p, "w") as f:
    for r in keep:
        f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
print(f"dropped {len(rows)-len(keep)} row(s), {len(keep)} remain")
PY
$PY -u scripts/run_all.py --config configs/jobshop_seeds.yaml --resume >> runs/jobshop_seeds/run_final.log 2>&1
say "re-run done"

# 3) NRA experiment (A/B/C families) -- fast
say "nra_experiment"
$PY -u scripts/nra_experiment.py > runs/_nra.log 2>&1
say "nra done (rc=$?)"

# 4) ill-conditioning WITH the shared objective -> runs/illcond_obj
say "illcond_experiment --objective"
$PY -u scripts/illcond_experiment.py --objective > runs/_illcond_obj.log 2>&1
say "illcond_obj done (rc=$?)"

say "chain complete; omt_tuning_probe NOT started (launched separately)"
