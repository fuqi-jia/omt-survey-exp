#!/usr/bin/env python3
"""Audit the complete 600-second FP cohort and its archived solver records."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import tarfile


ROOT = Path(__file__).resolve().parents[1]
FORMS = ("fp", "bvfp", "bv")
GROUPS = ("griggio", "heizmann", "ramalho", "schanda", "wintersteiger")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fp_bits(value):
    """Decode exact SMT-LIB IEEE literals, without rounding through Python floats."""
    match = re.fullmatch(r"\(\s*fp\s+#b([01])\s+(#b[01]+|#x[0-9a-fA-F]+)\s+"
                        r"(#b[01]+|#x[0-9a-fA-F]+)\s*\)", value)
    if match:
        sign, exponent, fraction = match.groups()
        def binary(token):
            width = len(token[2:]) * (4 if token.startswith("#x") else 1)
            return format(int(token[2:], 16 if token.startswith("#x") else 2), f"0{width}b")
        exponent, fraction = binary(exponent), binary(fraction)
        width = 1 + len(exponent) + len(fraction)
        return int(sign + exponent + fraction, 2), width
    match = re.fullmatch(r"\(\s*_\s+([+-]oo|[+-]zero)\s+(\d+)\s+(\d+)\s*\)", value)
    if match:
        special, eb, sb = match.groups()
        eb, sb = int(eb), int(sb)
        bits = (special[0] == "-") << (eb + sb - 1)
        if special.endswith("oo"):
            bits |= ((1 << eb) - 1) << (sb - 1)
        return bits, eb + sb
    raise ValueError(f"Unexpected native FP literal: {value}")


def key_to_bits(key, width):
    sign = 1 << (width - 1)
    return key ^ sign if key & sign else (~key & ((1 << width) - 1))


def audit(run):
    selection_path = ROOT / "benchmarks/public_fp/selection-full.json"
    selection = json.loads(selection_path.read_text())["selected"]
    environment = json.loads((run / "environment.json").read_text())
    assert len(selection) == 1120
    assert environment["selection_sha256"] == digest(selection_path)
    assert environment["solver_budget_s"] == 600
    assert environment["verification_budget_s_per_query"] == 600
    assert environment["preparation_budget_s"] == 600
    assert environment["z3"] == "5.3.3"
    assert environment["workers_per_host"] == 128
    assert environment["maximum_concurrent_routes"] == 256
    assert environment["memory_bytes"] == 4 * 1024**3
    assert environment["script_sha256"] == digest(ROOT / "scripts/public_fp_full_20261106.py")
    for host in environment["hosts"]:
        assert host["solver_budget_s"] == host["preparation_budget_s"] == 600
        assert host["verification_budget_s_per_query"] == 600
        assert host["script_sha256"] == environment["script_sha256"]
        assert len(set(host["physical_core_cpu_ids"])) == 128
        assert host["z3"] == "5.3.3"
        assert host["oms_sha256"] == environment["oms_sha256"]

    case_paths = sorted((run / "cases").glob("[0-9][0-9][0-9][0-9].json"))
    assert len(case_paths) == 1120
    counts = {form: Counter() for form in FORMS}
    grouped = {group: Counter(instances=0, fp=0, bvfp=0, bv=0) for group in GROUPS}
    rows, nan_records, zero_records, mismatches = [], [], [], []
    max_solve, max_verify, max_prepare = 0.0, 0.0, 0.0
    expected_prefixes = set()
    resumed_path = run / "resumed-completed-routes.json"
    resumed = json.loads(resumed_path.read_text())["routes"] if resumed_path.exists() else []
    with tarfile.open(run / "raw-logs.tar.gz") as archive:
        names, payloads = [], {}
        for member in archive:
            names.append(member.name)
            if member.name.endswith(".json"):
                payloads[member.name] = archive.extractfile(member).read()
        assert len(names) == len(set(names))
        for record in resumed:
            assert record["index"] % 2 == 0
            name = f"{record['index']:02d}/{record['form']}.final.json"
            data = payloads[name]
            assert hashlib.sha256(data).hexdigest() == record["final_sha256"]

        def raw(index, suffix):
            name = f"{index:02d}/{suffix}"
            assert name in payloads, name
            return json.loads(payloads[name])

        for index, path in enumerate(case_paths):
            case = json.loads(path.read_text())
            source = selection[index]
            assert case["index"] == index == int(path.stem)
            assert case["group"] == source["group"]
            assert case["upstream"] == source["upstream"]
            assert set(case["routes"]) == set(FORMS)
            expected_prefixes.add(f"{index:02d}")
            original = ROOT / "benchmarks/public_fp" / source["forms"]["fp"]["path"]
            assert digest(original) == source["forms"]["fp"]["sha256"]
            grouped[case["group"]]["instances"] += 1
            native_value, zeros, verified_keys = None, {}, {}
            if case["routes"]["fp"]["status"] == "nan":
                nan_records.append(dict(index=index, group=case["group"],
                    statuses={form: case["routes"][form]["status"] for form in FORMS}))
            for form in FORMS:
                rec = case["routes"][form]
                assert raw(index, form + ".final.json") == rec
                counts[form][rec["status"]] += 1
                verification = rec.get("verification", {})
                completed = rec["status"] == "verified"
                if completed:
                    grouped[case["group"]][form] += 1
                    assert verification["attainable"] == "sat"
                    assert verification["strictly_better"] == "unsat"
                    assert raw(index, form + ".verify.json") == verification
                    verify_process = raw(index, form + ".verify.process.json")
                    assert verify_process["returncode"] == 0
                    assert verify_process["process_status"] == "finished"
                    assert json.loads(verify_process["stdout"]) == verification
                    solve = raw(index, form + ".solve.json")
                    assert solve["status"] == "candidate"
                    if form == "fp":
                        process = solve
                        assert re.search(r"(?m)^\s*sat\s*$", process["stdout"])
                        assert "(objectives" in process["stdout"]
                        native_value = fp_bits(verification["value"])
                        bits, width = native_value
                        if bits & ((1 << (width - 1)) - 1) == 0:
                            zeros[form] = "-0" if bits >> (width - 1) else "+0"
                    else:
                        preparation = raw(index, form + ".prepare.json")
                        assert preparation["process_status"] == "finished"
                        assert preparation["returncode"] == 0
                        assert preparation["wall_s"] <= 600
                        assert json.loads(preparation["stdout"])["status"] == "prepared"
                        max_prepare = max(max_prepare, preparation["wall_s"])
                        process = raw(index, form + ".process.json")
                        assert json.loads(process["stdout"]) == solve
                        assert int(solve["lower"]) == int(solve["upper"]) == solve["key"]
                        assert int(verification["value"]) == solve["key"]
                        verified_keys[form] = solve["key"]
                        for width in (32, 64):
                            if solve["key"] == 1 << (width - 1):
                                zeros[form] = "+0"
                            elif solve["key"] == (1 << (width - 1)) - 1:
                                zeros[form] = "-0"
                    assert process["process_status"] == "finished"
                    assert process["returncode"] == 0
                    assert process["wall_s"] <= 600
                    assert rec["solve_s"] <= 600
                    assert 0 <= verification["attainable_s"] <= 600
                    assert 0 <= verification["strictly_better_s"] <= 600
                    max_solve = max(max_solve, rec["solve_s"])
                    max_verify = max(max_verify, verification["attainable_s"],
                                     verification["strictly_better_s"])
                rows.append(dict(index=index, group=case["group"], route=form,
                    host=environment["host_assignment"][str(index % 2)],
                    source=case["upstream"], source_sha256=source["forms"]["fp"]["sha256"],
                    adapter_status=rec["status"], paper_completed=completed,
                    solve_s=rec.get("solve_s"), attainable=verification.get("attainable"),
                    strictly_better=verification.get("strictly_better"),
                    attainable_s=verification.get("attainable_s"),
                    strictly_better_s=verification.get("strictly_better_s"),
                    value=verification.get("value"), raw_prefix=f"{index:02d}/"))
            if len(verified_keys) == 2 and len(set(verified_keys.values())) != 1:
                mismatches.append(dict(index=index, derived_keys=verified_keys))
            if native_value:
                bits, width = native_value
                mask = (1 << (width - 1)) - 1
                for form, key in verified_keys.items():
                    other = key_to_bits(key, width)
                    if bits != other and (bits & mask or other & mask):
                        mismatches.append(dict(index=index, route=form,
                            native_bits=bits, derived_bits=other, width=width))
            if zeros:
                zero_records.append(dict(index=index, group=case["group"], verified_zeros=zeros))
        assert {name.split("/")[0] for name in names} == expected_prefixes
    assert not mismatches, mismatches
    assert len(rows) == 3360
    assert all(sum(counter.values()) == 1120 for counter in counts.values())
    assert sum(group["instances"] for group in grouped.values()) == 1120
    report = dict(passed=True, instances=1120, routes=3360,
        status_counts={form: dict(counter) for form, counter in counts.items()},
        groups={group: dict(counter) for group, counter in grouped.items()},
        maximum_completed_solve_s=max_solve, maximum_completed_verification_query_s=max_verify,
        maximum_completed_preparation_s=max_prepare,
        all_counted_results_verified=True, objective_value_mismatches=mismatches,
        nan_records=nan_records, verified_zero_count=len(zero_records),
        verified_zero_records=zero_records,
        resumed_current_600_second_routes=len(resumed),
        zero_signs_agree_across_completed_routes=all(
            len(set(record["verified_zeros"].values())) == 1 for record in zero_records),
        input_manifest_sha256=digest(selection_path), raw_logs_sha256=digest(run / "raw-logs.tar.gz"))
    (run / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    with (run / "results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = []
    for form, label in zip(FORMS, ["OptiMathSAT: 原生浮点优化", "Z3: 浮点约束与位向量目标", "Z3: 全部转换为位向量"]):
        cells = [str(grouped[group][form]) for group in GROUPS]
        cells.append(str(counts[form]["verified"]))
        lines.append(label + " & " + " & ".join(cells) + r" \\")
    (run / "table-rows.tex").write_text("\n".join(lines) + "\n")
    print(json.dumps({"passed": True, "counts": {form: counter["verified"] for form, counter in counts.items()},
        "nan": len(nan_records), "zeros": len(zero_records)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, default=ROOT / "runs/public_fp_full_20261106_600s")
    audit(parser.parse_args().run.resolve())
