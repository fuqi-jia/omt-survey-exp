#!/usr/bin/env python3
"""NRA experiment: OMT(NRA) vs nonlinear programming (NLP) vs global MINLP.

Demonstrates that nonconvex / exact nonlinear optimization is a genuine strength
of OMT(NRA). Three solver kinds:
  * OMT(NRA): CDCL(OCAC) -- the complete OMT(NRA) engine (a cvc5 fork). Exact:
    returns the optimum as an algebraic number (e.g. sqrt(2)) and is GLOBAL.
  * local NLP: scipy.optimize (SLSQP) -- smooth local optimization; on a
    nonconvex problem it converges to a LOCAL optimum that depends on the start.
  * global MINLP: Gurobi (NonConvex=2) and SCIP -- spatial branch-and-bound,
    GLOBAL but floating-point (epsilon-approximate, no exact algebraic value).

Two instance kinds:
  (A) exact/irrational optimum:  max x  s.t.  x^2 <= k, x >= 0   ->  x* = sqrt(k).
      Convex, so every solver finds the global; the point is that only OMT(NRA)
      reports it EXACTLY (algebraic), the others give a float approximation.
  (B) nonconvex local trap:  min x  s.t. (2x-5)^2 >= 9, 0 <= x <= 5.
      Feasible set {x<=1} U {x>=4}; global x*=0. A local NLP started at x=5 is
      trapped at the local optimum x=4; OMT(NRA) and global MINLP find 0.

Run with the full-CPLEX/Gurobi env:  .venv-cplex/bin/python scripts/nra_experiment.py
(OCAC binary path via $OCAC or the default build location.)
Output: runs/nra/results.json + a printed table.
"""

import json
import math
import os
import re
import subprocess
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OMS = os.path.join(REPO, "tools", "optimathsat-1.7.4-linux-64-bit", "bin", "optimathsat")
# CDCL(OCAC) binary -- the complete OMT(NRA) solver. Set $OCAC, or drop the
# prebuilt static Linux x86-64 binary at tools/cdcl_ocac/cvc5. Download it from:
#   https://github.com/fuqi-jia/cdcl_ocac/releases/tag/v1.0.4-ocac-static
OCAC = os.environ.get("OCAC") or os.path.join(REPO, "tools", "cdcl_ocac", "cvc5")


# ---------------- instances ----------------
# (A) max x s.t. x^2<=k, x>=0  -> sqrt(k)
A_KS = [2, 3, 5, 7]
# (B) min x s.t. (2x-5)^2>=9, 0<=x<=5 -> 0 (local trap at 4); parametrized by gap center
B_INSTS = [(5, 9), (7, 16), (9, 25)]  # (a,b): (2x-a)^2>=b ; global x=0
# (C) OPTIMUM SHAPE: the two cases where an optimum does not exist as a value.
#   C1  min x  s.t.  x>0 /\ x*x>2      feasible set (sqrt2, oo); inf = sqrt2 NOT attained
#   C2  min x  s.t.  x*x>=1            feasible set (-oo,-1] u [1,oo); UNBOUNDED below
# Deliberately NO domain bound on x: an artificial lower bound would make both
# well-posed and destroy the very thing under test. C1 asks whether a solver can
# say "the infimum is sqrt2 but no feasible point attains it" (limit-optimal, the
# open endpoint ell*+0^+); C2 asks whether it can say "-infinity".
C_INSTS = ["C1_inf_unattained", "C2_unbounded_below"]


def true_sqrt(k):
    return math.sqrt(k)


# ---------------- OMT(NRA): CDCL(OCAC) ----------------
def ocac_solve(smt):
    f = tempfile.NamedTemporaryFile("w", suffix=".smt2", delete=False)
    f.write(smt); f.close()
    try:
        out = subprocess.run([OCAC, f.name], capture_output=True, text=True, timeout=60).stdout
    except Exception as e:
        os.unlink(f.name); return ("error", str(e)[:40])
    os.unlink(f.name)
    if "real_algebraic_number" in out:
        m = re.search(r"\(([-\d/]+),\s*([-\d/]+)\)>", out)   # bracketing interval
        return ("algebraic", out.strip())
    m = re.search(r"\(x\s+(\(/\s*-?\d+\s+\d+\)|-?\d+(?:\.\d+)?)\)", out)
    if m:
        return ("exact", m.group(1))
    return ("unknown", out.strip()[:60])


def ocac_A(k):
    return ocac_solve(f"""(set-logic OMT_QF_NRA)
(declare-fun x () Real)
(assert (and (>= x 0) (<= (* x x) {k})))
(maximize x)
(check-sat)
(get-objectives)
""")


def ocac_B(a, b):
    return ocac_solve(f"""(set-logic OMT_QF_NRA)
(declare-fun x () Real)
(assert (and (>= x 0) (<= x 5) (>= (* (- (* 2 x) {a}) (- (* 2 x) {a})) {b})))
(minimize x)
(check-sat)
(get-objectives)
""")


# ---------------- incumbent OMT(NRA): OptiMathSAT (incremental linearization) ----------------
def oms_solve(smt):
    f = tempfile.NamedTemporaryFile("w", suffix=".smt2", delete=False)
    f.write(smt); f.close()
    try:
        out = subprocess.run([OMS, "-optimization=TRUE", f.name],
                             capture_output=True, text=True, timeout=30).stdout
    except subprocess.TimeoutExpired:
        os.unlink(f.name); return "T/O"
    except Exception:
        os.unlink(f.name); return "error"
    os.unlink(f.name)
    m = re.search(r"\(x\s+([-\d./eE+]+)\)", out)
    return m.group(1) if m else "unknown"


def oms_A(k):
    return oms_solve(f"""(set-option :produce-models true)
(set-logic QF_NRA)
(declare-fun x () Real)
(assert (and (>= x 0) (<= (* x x) {k})))
(maximize x)
(check-sat)
(get-objectives)
""")


def oms_B(a, b):
    return oms_solve(f"""(set-option :produce-models true)
(set-logic QF_NRA)
(declare-fun x () Real)
(assert (and (>= x 0) (<= x 5) (>= (* (- (* 2 x) {a}) (- (* 2 x) {a})) {b})))
(minimize x)
(check-sat)
(get-objectives)
""")


# ---------------- local NLP: scipy ----------------
def scipy_A(k):
    from scipy.optimize import minimize
    r = minimize(lambda v: -v[0], [0.5], bounds=[(0, None)],
                 constraints=[{"type": "ineq", "fun": lambda v: k - v[0] ** 2}], method="SLSQP")
    return r.x[0]


def scipy_B(a, b, start):
    from scipy.optimize import minimize
    r = minimize(lambda v: v[0], [start], bounds=[(0, 5)],
                 constraints=[{"type": "ineq", "fun": lambda v: (2 * v[0] - a) ** 2 - b}], method="SLSQP")
    return r.x[0]


# ---------------- global MINLP: Gurobi (NonConvex=2) ----------------
def gurobi_A(k):
    try:
        import gurobipy as gp
        from gurobipy import GRB
        m = gp.Model(); m.Params.OutputFlag = 0; m.Params.NonConvex = 2
        x = m.addVar(lb=0, ub=10); m.setObjective(x, GRB.MAXIMIZE)
        m.addConstr(x * x <= k); m.optimize()
        return x.X if m.SolCount else None
    except Exception as e:
        return None


def gurobi_B(a, b):
    try:
        import gurobipy as gp
        from gurobipy import GRB
        m = gp.Model(); m.Params.OutputFlag = 0; m.Params.NonConvex = 2
        x = m.addVar(lb=0, ub=5); m.setObjective(x, GRB.MINIMIZE)
        m.addConstr((2 * x - a) * (2 * x - a) >= b); m.optimize()
        return x.X if m.SolCount else None
    except Exception:
        return None


# ---------------- (C) optimum-shape probes ----------------
# Every C-family call keeps the solver's RAW output. The question here is not
# "how fast" nor even "which number", but "does the solver TELL you that no
# optimal value exists". A parsed number would throw that away.

C_SMT = {                                   # body shared by OCAC and OptiMathSAT
    "C1_inf_unattained": "(assert (and (> x 0) (> (* x x) 2)))",
    "C2_unbounded_below": "(assert (>= (* x x) 1))",
}
C_TRUTH = {                                 # what the mathematics says
    "C1_inf_unattained": {"inf": math.sqrt(2), "attained": False, "bounded": True},
    "C2_unbounded_below": {"inf": None, "attained": False, "bounded": False},
}

# The objective is asked for in TWO semantically identical ways, because on the
# tested CDCL(OCAC) build they do not behave the same:
#
#   bare      (minimize x)        x is a declared variable
#   wrapped   (minimize (+ x 0))  the same quantity as a compound term
#
# With the wrapped form OCAC answers both cases correctly -- sqrt2+epsilon for the
# unattained infimum, -oo for the unbounded one. With the bare form it returns a
# feasible check-sat witness instead. Reporting only one form would either hide a
# real front-end trigger or slander a working algorithm, so both are recorded.
OBJ_FORMS = [("bare", "(minimize x)"), ("wrapped", "(minimize (+ x 0))")]


def _run_raw(cmd, timeout=60):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return "<timeout>"
    except Exception as e:
        return f"<error: {e}>"


def _smt_file(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".smt2", delete=False)
    f.write(text); f.close()
    return f.name


def classify_C(raw, inst):
    """Map raw solver output onto the four answers this experiment cares about.

    reported_limit  -- says the bound is approached but not attained (eps / open
                       endpoint / "limit"), i.e. the mathematically right answer for C1
    reported_unbnd  -- says unbounded / -infinity, the right answer for C2
    feasible_only   -- returns sat plus some feasible value, WITHOUT flagging either
                       (a reader who trusts the number is misled)
    """
    low = raw.lower()
    if "unbounded" in low or "-oo" in low or "-inf" in low or "infeasible or unbounded" in low:
        return "reported_unbnd"
    if "epsilon" in low or "limit" in low or "+ eps" in low or "0^+" in low:
        return "reported_limit"
    if raw.startswith("unsat"):
        return "unsat"
    if "error" in low or "segfault" in low or raw.startswith("<"):
        return "error"
    m = re.search(r"\(x\s+\(?-?\s*([\d.]+)", raw)
    return "feasible_only" if m else "unknown"


def ocac_C(inst, obj):
    smt = (f"(set-logic OMT_QF_NRA)\n(declare-fun x () Real)\n{C_SMT[inst]}\n"
           f"{obj}\n(check-sat)\n(get-objectives)\n")
    fn = _smt_file(smt); raw = _run_raw([OCAC, fn]); os.unlink(fn)
    return classify_C(raw, inst), raw


def oms_C(inst, obj):
    smt = ("(set-option :produce-models true)\n(set-logic QF_NRA)\n"
           f"(declare-fun x () Real)\n{C_SMT[inst]}\n"
           f"{obj}\n(check-sat)\n(get-objectives)\n")
    fn = _smt_file(smt); raw = _run_raw([OMS, "-optimization=TRUE", fn]); os.unlink(fn)
    return classify_C(raw, inst), raw


def scipy_C(inst, start=5.0):
    """Local NLP from x0=5. No bounds -- C2 must be free to run to -infinity."""
    from scipy.optimize import minimize
    cons = ([{"type": "ineq", "fun": lambda v: v[0] ** 2 - 2},
             {"type": "ineq", "fun": lambda v: v[0]}]
            if inst == "C1_inf_unattained"
            else [{"type": "ineq", "fun": lambda v: v[0] ** 2 - 1}])
    r = minimize(lambda v: v[0], [start], constraints=cons, method="SLSQP")
    return {"x": float(r.x[0]), "success": bool(r.success), "status": int(r.status),
            "message": str(r.message)[:80]}


def gurobi_C(inst):
    """Gurobi spatial B&B. Note it cannot express a STRICT inequality, so for C1 it
    necessarily solves the CLOSURE (x>=0 /\\ x*x>=2), whose minimum sqrt2 IS attained
    -- the relaxation is itself the finding, not a bug."""
    try:
        import gurobipy as gp
        from gurobipy import GRB
        m = gp.Model(); m.Params.OutputFlag = 0; m.Params.NonConvex = 2
        # free variable: an implicit lb=0 would silently make C2 bounded
        x = m.addVar(lb=-GRB.INFINITY, ub=GRB.INFINITY)
        if inst == "C1_inf_unattained":
            m.addConstr(x >= 0); m.addConstr(x * x >= 2)
        else:
            m.addConstr(x * x >= 1)
        m.setObjective(x, GRB.MINIMIZE); m.optimize()
        st = {GRB.OPTIMAL: "OPTIMAL", GRB.UNBOUNDED: "UNBOUNDED",
              GRB.INF_OR_UNBD: "INF_OR_UNBD", GRB.INFEASIBLE: "INFEASIBLE"}.get(
                  m.Status, f"status_{m.Status}")
        return {"status": st, "x": (x.X if m.SolCount else None),
                "objbound": (m.ObjBound if m.SolCount or m.Status == GRB.OPTIMAL else None)}
    except Exception as e:
        return {"status": f"error: {str(e)[:60]}", "x": None, "objbound": None}


def fmt(v):
    return "--" if v is None else f"{v:.4f}"


def main():
    out = os.path.join(REPO, "runs", "nra"); os.makedirs(out, exist_ok=True)
    rows = []
    print(f"OCAC = {OCAC}\n")
    print("== (A) max x s.t. x^2<=k  (x*=sqrt k, irrational; convex -> all global) ==")
    print(f"  {'k':>3} {'true':>9} {'OCAC':>12} {'OptiMSAT':>10} {'scipy':>9} {'gurobi':>9}")
    for k in A_KS:
        oc = ocac_A(k); om = oms_A(k); sp = scipy_A(k); gu = gurobi_A(k)
        exact = oc[0] == "algebraic" or oc[0] == "exact"
        rows.append({"inst": f"A_sqrt{k}", "true": true_sqrt(k), "ocac": oc[0],
                     "ocac_exact": exact, "optimathsat": om, "scipy": sp, "gurobi": gu})
        tag = "algebraic" if oc[0] == "algebraic" else oc[0]
        print(f"  {k:>3} {true_sqrt(k):>9.4f} {tag:>12} {om:>10} {fmt(sp):>9} {fmt(gu):>9}")
    print("\n== (B) min x s.t. (2x-a)^2>=b  (nonconvex; global x*=0, local trap x=a/2-...) ==")
    print(f"  {'(a,b)':>8} {'global':>7} {'OCAC':>7} {'scipy@hi':>9} {'scipy@lo':>9} {'gurobi':>8}")
    for (a, b) in B_INSTS:
        oc = ocac_B(a, b); om = oms_B(a, b); sp_hi = scipy_B(a, b, 5.0); sp_lo = scipy_B(a, b, 0.2); gu = gurobi_B(a, b)
        ocv = oc[1] if oc[0] in ("exact",) else oc[0]
        rows.append({"inst": f"B_{a}_{b}", "global": 0.0, "ocac": oc[0], "ocac_val": oc[1],
                     "optimathsat": om, "scipy_hi": sp_hi, "scipy_lo": sp_lo, "gurobi": gu})
        print(f"  ({a},{b})  {0.0:>6.1f} {str(ocv):>7} {str(om):>9} {fmt(sp_hi):>9} {fmt(sp_lo):>9} {fmt(gu):>8}")
    print("\n== (C) optimum SHAPE: infimum not attained / unbounded ==")
    print("   C1: min x s.t. x>0 /\\ x*x>2   -> inf = sqrt2 = 1.4142, NOT attained")
    print("   C2: min x s.t. x*x>=1         -> unbounded below (-inf)")
    print("   objective asked twice: bare '(minimize x)' vs wrapped '(minimize (+ x 0))'")
    print(f"  {'inst':>4} {'obj':>8} {'CDCL(OCAC)':>16} {'OptiMathSAT':>16}")
    c_rows = []
    for inst in C_INSTS:
        rec = {"inst": inst, "truth": C_TRUTH[inst], "by_objective_form": {}}
        for form, obj in OBJ_FORMS:
            oc_c, oc_raw = ocac_C(inst, obj)
            om_c, om_raw = oms_C(inst, obj)
            rec["by_objective_form"][form] = {
                "smtlib": obj,
                "ocac": {"verdict": oc_c, "raw": oc_raw},
                "optimathsat": {"verdict": om_c, "raw": om_raw},
            }
            print(f"  {inst[:2]:>4} {form:>8} {oc_c:>16} {om_c:>16}")
        rec["scipy_slsqp_start5"] = scipy_C(inst)
        rec["gurobi_nonconvex"] = gurobi_C(inst)
        sp, gu = rec["scipy_slsqp_start5"], rec["gurobi_nonconvex"]
        print(f"       {'scipy@5':>8} {sp['x']:>16.4f} {'gurobi':>8} "
              f"{gu['status']}" + (f"/{gu['x']:.4f}" if gu["x"] is not None else ""))
        c_rows.append(rec); rows.append(rec)
    print("\n  raw output (kept verbatim in results.json):")
    for r in c_rows:
        print(f"   {r['inst']}")
        for form in r["by_objective_form"]:
            for eng in ("ocac", "optimathsat"):
                raw = r["by_objective_form"][form][eng]["raw"][:110].replace(chr(10), " | ")
                print(f"     {form:<8}{eng:<12}: {raw}")
    json.dump(rows, open(os.path.join(out, "results.json"), "w"), indent=1)
    print(f"\nscipy@hi = local NLP started at x=5 (trap); scipy@lo = started at x=0.2.")
    print(f"Wrote {os.path.relpath(out, REPO)}/results.json")


if __name__ == "__main__":
    main()
