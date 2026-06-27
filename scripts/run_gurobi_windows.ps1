# =====================================================================
# run_gurobi_windows.ps1
#   Run the full-Gurobi large-scale linear comparison on Windows.
#
#   The full Gurobi license is NODE-locked to this Windows host, so it must run
#   on Windows (not WSL). This script creates a minimal Windows venv with only
#   gurobipy, points it at the node-locked license, and runs
#   scripts/gurobi_linear_windows.py.
#
#   Usage (from PowerShell):
#       cd D:\D_Study\ISCAS\projects\GOMT\omt-survey-exp
#       powershell -ExecutionPolicy Bypass -File scripts\run_gurobi_windows.ps1
# =====================================================================
$ErrorActionPreference = "Stop"

# --- paths (edit if your install dirs differ) ---
$Repo = "D:\D_Study\ISCAS\projects\GOMT\omt-survey-exp"
$Lic  = "D:\D_Softwares\Gurobi13\win64\bin\gurobi.lic"

Set-Location $Repo

if (-not (Test-Path $Lic)) {
    Write-Error "Gurobi license not found at $Lic -- edit `$Lic in this script."
}

# --- 1. Windows venv (only gurobipy needed; the runner is self-contained) ---
$Py = Join-Path $Repo ".venv-win\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "==> creating Windows venv (.venv-win)"
    py -m venv .venv-win
}
Write-Host "==> installing gurobipy"
& $Py -m pip install --upgrade pip --quiet
& $Py -m pip install --quiet "gurobipy==13.*"

# --- 2. point at the node-locked full license ---
$env:GRB_LICENSE_FILE = $Lic
Write-Host "==> GRB_LICENSE_FILE = $Lic"

# --- 3. run the large-scale linear comparison ---
Write-Host "==> running scripts\gurobi_linear_windows.py`n"
& $Py scripts\gurobi_linear_windows.py

Write-Host "`n==> done. Results in runs\gurobi_win\results.json"
