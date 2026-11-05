#!/usr/bin/env python3
"""Package completed 600-second shards, then merge their predetermined cohorts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import time


ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def pack(run, parity, wait):
    indices = list(range(parity, 1120, 2))
    try:
        while True:
            path = run / "summary.json"
            summary = json.loads(path.read_text()) if path.exists() else {}
            if summary.get("completed_routes") == 1680:
                break
            if not wait:
                raise RuntimeError("Shard is incomplete")
            launch = json.loads((run / "launch.json").read_text())
            if not Path(f"/proc/{launch['pid']}").exists():
                raise RuntimeError("Runner exited before the shard completed")
            if list((run / "cases").glob("*.error.json")):
                raise RuntimeError("Infrastructure error recorded")
            time.sleep(15)
        assert summary["completed_instances"] == 560
        assert json.loads((run / "selected-indices.json").read_text()) == indices
        assert sorted(int(path.stem) for path in (run / "cases").glob("*.json")) == indices
        for index in indices:
            case = json.loads((run / "cases" / f"{index:04d}.json").read_text())
            assert case["index"] == index
            assert set(case["routes"]) == {"fp", "bvfp", "bv"}
        with tarfile.open(run / "raw-logs.tar.gz", "w:gz", compresslevel=6) as archive:
            for index in indices:
                for path in sorted((run / f"{index:02d}").iterdir()):
                    if path.name.endswith((".json", ".stdout", ".stderr")):
                        archive.add(path, arcname=f"{index:02d}/{path.name}", recursive=False)
        with tarfile.open(run / "cases.tar.gz", "w:gz", compresslevel=6) as archive:
            for index in indices:
                path = run / "cases" / f"{index:04d}.json"
                archive.add(path, arcname=f"cases/{path.name}", recursive=False)
        shutil.copy2(ROOT / "scripts/public_fp_full_20261106.py", run / "runner.py")
        memory = next(line for line in Path("/proc/meminfo").read_text().splitlines()
                      if line.startswith("MemTotal:"))
        delivery = dict(parity=parity, instances=560, routes=1680,
            selected_indices_sha256=digest(run / "selected-indices.json"),
            raw_logs_sha256=digest(run / "raw-logs.tar.gz"),
            cases_sha256=digest(run / "cases.tar.gz"),
            runner_sha256=digest(run / "runner.py"),
            physical_memory_bytes=int(memory.split()[1]) * 1024,
            finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        library = ROOT / "tools/z3-5.3.3/python/z3/lib/libz3.so"
        delivery["z3_library_sha256"] = digest(library)
        save(run / "delivery.json", delivery)
        save(run / "READY.json", delivery)
        print(json.dumps(delivery), flush=True)
    except Exception as error:
        save(run / "packaging-error.json", dict(error=repr(error)))
        raise


def merge(sources, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / "cases").mkdir(exist_ok=True)
    environments, deliveries, seen, summaries = [], [], set(), []
    host_assignment = {}
    for parity, source in enumerate(sources):
        delivery = json.loads((source / "delivery.json").read_text())
        assert delivery["parity"] == parity
        assert delivery["instances"] == 560 and delivery["routes"] == 1680
        for name, key in [("raw-logs.tar.gz", "raw_logs_sha256"),
                          ("cases.tar.gz", "cases_sha256"), ("runner.py", "runner_sha256"),
                          ("selected-indices.json", "selected_indices_sha256")]:
            assert digest(source / name) == delivery[key]
        indices = json.loads((source / "selected-indices.json").read_text())
        assert indices == list(range(parity, 1120, 2))
        environment = json.loads((source / "environment.json").read_text())
        environments.append(environment)
        deliveries.append(delivery)
        host_assignment[str(parity)] = environment["hostname"]
        with tarfile.open(source / "cases.tar.gz") as archive:
            for member in archive:
                assert member.isfile() and member.name.startswith("cases/")
                assert Path(member.name).parent.as_posix() == "cases"
                index = int(Path(member.name).stem)
                assert index % 2 == parity and index not in seen
                seen.add(index)
                data = archive.extractfile(member).read()
                case = json.loads(data)
                assert case["index"] == index
                assert set(case["routes"]) == {"fp", "bvfp", "bv"}
                target = output / member.name
                if target.exists():
                    assert target.read_bytes() == data
                else:
                    target.write_bytes(data)
                summaries.append(case)
    assert seen == set(range(1120))
    assert len({delivery["z3_library_sha256"] for delivery in deliveries}) == 1
    assert all("Xeon(R) Platinum 8153" in env["cpu"] for env in environments)
    common = ["z3", "optimathsat", "solver_budget_s", "preparation_budget_s",
              "verification_budget_s_per_query", "verification_process_budget_s", "memory_bytes",
              "selection_sha256", "oms_sha256", "script_sha256"]
    for key in common:
        assert environments[0][key] == environments[1][key], key
    environment = {key: environments[0][key] for key in common}
    environment.update(date="2026-11-06", workers_per_host=128, maximum_concurrent_routes=256,
        host_assignment=host_assignment, hosts=environments,
        z3_library_sha256=deliveries[0]["z3_library_sha256"],
        partition="Zero-based even indices on panda1; odd indices on panda4.")
    save(output / "environment.json", environment)
    save(output / "shard-manifest.json", dict(partition=environment["partition"],
        hosts=host_assignment, shards=deliveries))
    with tarfile.open(output / "raw-logs.tar.gz", "w:gz", compresslevel=6) as merged:
        seen_members = set()
        for parity, source in enumerate(sources):
            with tarfile.open(source / "raw-logs.tar.gz") as archive:
                for member in archive:
                    assert member.isfile()
                    assert len(Path(member.name).parts) == 2
                    assert int(Path(member.name).parts[0]) % 2 == parity
                    assert member.name not in seen_members
                    seen_members.add(member.name)
                    merged.addfile(member, archive.extractfile(member))
    counts = {form: Counter() for form in ["fp", "bvfp", "bv"]}
    groups = {}
    for case in summaries:
        group = groups.setdefault(case["group"], dict(instances=0, fp=0, bvfp=0, bv=0))
        group["instances"] += 1
        for form, record in case["routes"].items():
            counts[form][record["status"]] += 1
            group[form] += record["status"] == "verified"
    summary = dict(population=1120, completed_instances=1120, completed_routes=3360,
        groups=groups, route_status_counts={form: dict(counter) for form, counter in counts.items()})
    save(output / "summary.json", summary)
    shutil.copy2(sources[0] / "runner.py", output / "runner.py")
    save(output / "delivery.json", dict(instances=1120, routes=3360,
        raw_logs_sha256=digest(output / "raw-logs.tar.gz"),
        raw_logs_bytes=(output / "raw-logs.tar.gz").stat().st_size,
        runner_sha256=digest(output / "runner.py"), complete_shards=2))
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    pack_parser = sub.add_parser("pack")
    pack_parser.add_argument("--run", type=Path, required=True)
    pack_parser.add_argument("--parity", type=int, choices=[0, 1], required=True)
    pack_parser.add_argument("--wait", action="store_true")
    merge_parser = sub.add_parser("merge")
    merge_parser.add_argument("--source-a", type=Path, required=True)
    merge_parser.add_argument("--source-b", type=Path, required=True)
    merge_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "pack":
        pack(args.run.resolve(), args.parity, args.wait)
    else:
        merge([args.source_a.resolve(), args.source_b.resolve()], args.output.resolve())
