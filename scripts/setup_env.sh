#!/usr/bin/env bash
# Reproducible environment setup for the OMT-survey experiment.
#
# Creates a local virtualenv (.venv), installs the open-source solver stack, and
# fetches the OptiMathSAT 1.7.4 binary (the distro PATH build often ships without
# optimization support). Idempotent: safe to re-run.
#
#   bash scripts/setup_env.sh
#
# Solvers that need a license (Gurobi, CPLEX) and Chuffed are NOT installed here;
# the runner auto-detects and uses them if they are present on PATH / in PuLP.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> [1/3] Python virtualenv (.venv)"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install -r requirements.txt

echo "==> [2/3] OptiMathSAT 1.7.4 (OMT binary)"
OMT_DIR="tools/optimathsat-1.7.4-linux-64-bit"
if [ ! -x "$OMT_DIR/bin/optimathsat" ]; then
  mkdir -p tools
  URL="https://optimathsat.disi.unitn.it/releases/optimathsat-1.7.4/optimathsat-1.7.4-linux-64-bit.tar.gz"
  echo "    downloading $URL"
  ( cd tools && wget -q "$URL" -O optimathsat-1.7.4.tar.gz && tar xzf optimathsat-1.7.4.tar.gz )
fi
echo "    optimathsat: $("$OMT_DIR/bin/optimathsat" -version 2>/dev/null | head -1)"

echo "==> [3/3] Detected solvers"
.venv/bin/python - <<'PY'
import sys, os
sys.path.insert(0, os.getcwd())
from experiments.solvers import detect_solvers
for s in detect_solvers():
    print(f"    {s.paradigm:5} {s.name}")
PY

cat <<'EOF'

Setup complete. Next:
  .venv/bin/python scripts/gen_benchmarks.py --config configs/wsl.yaml
  .venv/bin/python scripts/run_all.py       --config configs/wsl.yaml
  .venv/bin/python scripts/analyze.py       --config configs/wsl.yaml
EOF
