"""M1 -- run `Task.formcheck` over SWE-bench Verified, one image at a time.

Every task takes the same path M0 established and gated: verifiers' own
`_run_check(task, cfg, "formcheck")`, `DockerRuntime`, the image resolved through
`resolve_runtime_config` from `task.data.image`. Nothing about that path is
re-implemented here. What this file adds is everything around it -- selection,
rotation, resume, timeouts, and a record per task that an aggregate can be
computed from without re-reading a log.

DESIGN CONSTRAINT, MEASURED RATHER THAN ASSUMED. M0 measured 3.841 GB pulled and
discarded per task, 0.37 GiB of host RAM, and ~13% container overhead over the
subprocess rig. So the scarce resource is disk, the worker count is a function of
disk, and nothing here is tuned for compute.

FAILURE IS REPORTED, NEVER INFERRED. A task whose control does not reach 1.0 is
`unchecked` and contributes no rows -- not a witness, not a clean. That rule
already cost this project four "witnesses", two of them false (`writeup.md` 4.1),
and it is enforced in the hook rather than here so that it cannot be skipped by a
caller.

Usage:
    ~/.venv-fc/bin/python scale/run.py --limit 5            # the pilot
    ~/.venv-fc/bin/python scale/run.py --instance-id <id>   # reproduce exactly one
    ~/.venv-fc/bin/python scale/run.py --resume             # skip finished tasks
    tail -f scale/progress.jsonl
"""

import argparse
import asyncio
import json
import os
import random
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "repro"))

import verifiers.v1 as vf  # noqa: E402
from verifiers.v1.cli.validate import _run_check  # noqa: E402
from verifiers.v1.configs.cli.validate import ValidateConfig  # noqa: E402
from verifiers.v1.runtimes import DockerConfig  # noqa: E402

import rotation  # noqa: E402
from container_task import (  # noqa: E402
    ContainerData, SweBenchFormcheckTask, build_task_spec,
)
from images import image_ref  # noqa: E402

# `records/`, not `results/`: `scale/results/` holds the M0 artifact, which has
# a different schema and is the committed evidence for the container gate.
# Writing M1 records over it would destroy the baseline this run builds on.
RESULTS = os.path.join(HERE, "records")
PROGRESS = os.path.join(HERE, "progress.jsonl")
LEASES = os.path.join(HERE, ".leases")
ELIGIBLE = os.path.join(HERE, "eligible.jsonl")

DEFAULT_TASK_TIMEOUT = 45 * 60


class Progress:
    """Append-only, one JSON object per line, flushed on every write.

    Flushed because the point of it is to be tailed while the run is going; a
    buffered progress log tells you where the run was, not where it is.
    """

    def __init__(self, path):
        self.path = path
        self._lock = asyncio.Lock()

    def write(self, **fields):
        fields.setdefault("t", round(time.time(), 3))
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(fields, sort_keys=True,
                               separators=(",", ":")) + "\n")
            f.flush()


def on_prime_hub(instance_id: str):
    """Whether this task exists as an environment on Prime's hub.

    Returns `None`, always, and that is a result rather than a stub. Deciding it
    needs the hub's environment index; nothing in this repo, in `verifiers` or in
    `swebench` can answer it offline, and no SWE-bench taskset lives in
    `verifiers` any more to be consulted (v0 removed 2026-08-31, `66a6064`). A
    guess here would propagate into a headline as if it had been checked, so the
    field is null and the reason travels with it.
    """
    return None


def load_instances():
    from datasets import load_dataset
    ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    return {row["instance_id"]: row for row in ds}


def eligible_ids():
    if not os.path.exists(ELIGIBLE):
        raise SystemExit(
            f"{ELIGIBLE} not found -- run `scale/eligibility.py` first. Eligibility "
            "is decided from the gold patches before any container starts.")
    ids = []
    with open(ELIGIBLE, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row["eligible"]:
                ids.append(row["instance_id"])
    return ids


def record_path(instance_id):
    return os.path.join(RESULTS, f"{instance_id}.json")


def is_complete(instance_id):
    """A record counts as done only if it says so itself.

    Presence of the file is not enough: a run killed mid-write leaves a partial
    file, and resuming past it would silently drop a task from the denominator.
    """
    try:
        with open(record_path(instance_id), encoding="utf-8") as f:
            return json.load(f).get("completed") is True
    except (OSError, ValueError):
        return False


def write_record(record):
    """Atomic: write beside, then rename. A reader tailing the results directory
    never sees half a record, and a crash mid-write cannot corrupt a finished
    one."""
    os.makedirs(RESULTS, exist_ok=True)
    path = record_path(record["instance_id"])
    tmp = path + ".partial"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(record, f, indent=2, sort_keys=True)
    os.replace(tmp, path)
    return path


def build_record(instance_id, image, spec, row, task, elapsed, error=None):
    """The per-task record. Every field an aggregate needs is here, computed on
    the path that produced the verdicts."""
    rows = list(getattr(task, "formcheck_rows", []) or [])
    log = list(getattr(task, "formcheck_log", []) or [])
    control = next((entry for entry in log if entry[0] == "<control>"), None)
    control_ok = bool(control and control[1] == "OK")

    witnesses = [r for r in rows if r["verdict"] == "WITNESS"]
    for w in witnesses:
        graded = w.get("graded_report") or {}
        analysis = w.get("failure_analysis") or {}
        # Which side of the suite the witness landed on. The earlier version
        # derived this from `p2p_fail == 0` alone -- the same shape as the bug
        # in `CHANGES.md` 13, comparing a count without asking what the failures
        # said. It is now read off the attributed failures, so `p2p_coupling`
        # means "P2P tests failed AND each one names the renamed symbol", which
        # is the `writeup.md` 6.2 class, rather than merely "P2P failed".
        w["f2p_fail"] = graded.get("f2p_fail")
        w["p2p_fail"] = graded.get("p2p_fail")
        coupled = set(analysis.get("coupled") or ())
        p2p_coupled = [t for t in (graded.get("p2p_failing") or []) if t in coupled]
        w["p2p_coupled_tests"] = p2p_coupled
        w["all_failures_attributed"] = analysis.get("all_reference_the_symbol")
        w["witness_side"] = (
            None if not graded else
            "p2p_coupling" if p2p_coupled else
            "f2p_only" if not graded.get("p2p_fail") else "p2p_unattributed")

    operators = sorted({r["operator"] for r in rows})
    return {
        "instance_id": instance_id,
        "image": image,
        "repo": spec["meta"]["repo"],
        "version": spec["meta"]["version"],
        "targets": spec["targets"],
        "n_targets": len(spec["targets"]),
        "multi_target": len(spec["targets"]) > 1,
        # Did the image pull, the container start and `Task.setup` complete?
        "mountable": row is not None and row.get("error_type") is None,
        "control": {
            "passed": control_ok,
            "reason": control[2] if control else "control never ran",
        },
        "row": row,
        "rows": rows,
        "log": log,
        "operators_with_anchors": [
            op for op in operators
            if any(r["operator"] == op and r["verdict"] != "NOT_APPLICABLE"
                   for r in rows)
        ],
        "operators_not_applicable": [
            op for op in operators
            if all(r["verdict"] == "NOT_APPLICABLE"
                   for r in rows if r["operator"] == op)
        ],
        "witnesses": witnesses,
        "on_prime_hub": on_prime_hub(instance_id),
        "on_prime_hub_reason": (
            "not resolvable offline; no hub environment index is reachable from "
            "this repo, verifiers or swebench"),
        "elapsed_seconds": elapsed,
        "error": error,
        "completed": True,
    }


async def run_one(instance, leases, progress, timeout, baseline_free=0):
    instance_id = instance["instance_id"]
    spec = build_task_spec(instance)
    image = image_ref(instance_id)
    t0 = time.time()
    progress.write(event="start", instance_id=instance_id, image=image,
                   n_targets=len(spec["targets"]))

    if not spec["targets"]:
        record = build_record(instance_id, image, spec, None, None,
                              round(time.time() - t0, 2),
                              error="no production Python file in the gold patch")
        write_record(record)
        progress.write(event="skipped", instance_id=instance_id,
                       reason="no production Python target")
        return record

    task = None
    row = None
    error = None
    try:
        async with rotation.ImageLease(image, instance_id, leases, progress.write):
            cfg = ValidateConfig(taskset={"id": "harbor"},
                                 runtime=DockerConfig(), only_formcheck=True)
            data = ContainerData(idx=0, name=instance_id, prompt="",
                                 image=image, workdir="/testbed")
            task = SweBenchFormcheckTask(data, spec)
            row = await asyncio.wait_for(
                _run_check(task, cfg, "formcheck"), timeout)
    except asyncio.TimeoutError:
        error = f"task exceeded {timeout}s"
    except Exception as exc:  # noqa: BLE001 - one task's failure is a row, not a crash
        error = f"{type(exc).__name__}: {exc}"
        progress.write(event="error", instance_id=instance_id, error=error,
                       traceback=traceback.format_exc()[-2000:])

    # THE PER-TASK BUDGET IS CHECKED STRUCTURALLY, NOT BY A FREE-SPACE DELTA.
    #
    # The first version compared free space before and after the task. That is
    # wrong under concurrency, and M2 proved it: `flask-5014` finished while the
    # other worker still held the 3.57 GiB `pytest-10356` image, so the global
    # delta charged that image to flask -- 3664 MiB of "residual" against a
    # 256 MiB threshold -- and the run aborted on a task that had cleaned up
    # perfectly. A global measurement cannot answer a per-task question while
    # anything else is running.
    #
    # What IS attributable to this task is whether ITS image and ITS containers
    # are gone. Exact, cheap, and unaffected by other workers.
    leaked_containers = rotation.containers_for(image)
    leaked_image = rotation.image_present(image)
    orphan_reclaimed = 0
    if leaked_containers or leaked_image:
        rotation.reconcile_containers(set())
        orphan_reclaimed = rotation.reclaim_orphans()
        leaked_containers = rotation.containers_for(image)
        leaked_image = rotation.image_present(image)

    # The run-wide budget is still checked, but only when it is meaningful: with
    # no other lease live, free space is attributable to the run as a whole and a
    # shortfall against its baseline is real accumulation.
    residual = 0
    if not leases.live_refs():
        residual = max(0, baseline_free - rotation.free_bytes())
        if residual > rotation.RESIDUAL_ABORT_MIB * 1024**2:
            orphan_reclaimed += rotation.reclaim_orphans()
            residual = max(0, baseline_free - rotation.free_bytes())

    record = build_record(instance_id, image, spec, row, task,
                          round(time.time() - t0, 2), error)
    record["disk_residual_bytes"] = residual
    record["disk_orphan_reclaimed_bytes"] = orphan_reclaimed
    record["leaked_image"] = leaked_image
    record["leaked_containers"] = leaked_containers
    write_record(record)
    progress.write(
        event="done", instance_id=instance_id,
        reason=(row or {}).get("reason"), error=error,
        control=record["control"]["passed"],
        witnesses=len(record["witnesses"]),
        seconds=record["elapsed_seconds"],
        disk_residual_mib=round(residual / 1024**2, 1),
        orphan_reclaimed_mib=round(orphan_reclaimed / 1024**2, 1),
        leaked_image=leaked_image, leaked_containers=leaked_containers,
        free_gib=round(rotation.free_bytes() / 1024**3, 2))

    if leaked_image or leaked_containers:
        progress.write(event="abort", instance_id=instance_id,
                       reason="the task's own image or container survived it",
                       leaked_image=leaked_image,
                       leaked_containers=leaked_containers)
        raise rotation.DiskBudgetError(
            f"{instance_id}: its own image or container outlived the task and "
            f"could not be reclaimed (image_present={leaked_image}, "
            f"containers={leaked_containers}). Stopping: at ~4 GiB each these "
            "fill the budget silently and the next pull fails looking like a "
            "transport error.")
    if residual > rotation.RESIDUAL_ABORT_MIB * 1024**2:
        progress.write(event="abort", instance_id=instance_id,
                       reason="run-wide disk did not return to baseline",
                       residual_mib=round(residual / 1024**2, 1))
        raise rotation.DiskBudgetError(
            f"{instance_id}: with no other task running, "
            f"{residual / 1024**2:.0f} MiB has not come back since the run "
            f"started (threshold {rotation.RESIDUAL_ABORT_MIB} MiB). Stopping "
            "rather than continuing on a budget that cannot be accounted for.")
    return record


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance-id", action="append", default=[],
                    help="run exactly these; repeatable. Reproduces one task.")
    ap.add_argument("--ids-file",
                    help="file of instance ids, one per line, `#` comments "
                         "ignored. Used by M3, whose sample is frozen to "
                         "scale/ids_50.txt and committed before the run.")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--seed", type=int, default=0,
                    help="sampling seed; recorded, so a pilot is reproducible")
    ap.add_argument("--workers", type=int, default=None,
                    help="default: as many images as fit on disk")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TASK_TIMEOUT)
    ap.add_argument("--resume", action="store_true",
                    help="skip tasks whose record says completed")
    args = ap.parse_args()

    os.makedirs(RESULTS, exist_ok=True)
    leases = rotation.Leases(LEASES)
    progress = Progress(PROGRESS)

    instances = load_instances()
    if args.ids_file:
        with open(args.ids_file, encoding="utf-8") as f:
            ids = [ln.strip() for ln in f
                   if ln.strip() and not ln.startswith("#")]
    elif args.instance_id:
        ids = list(args.instance_id)
    if args.ids_file or args.instance_id:
        missing = [i for i in ids if i not in instances]
        if missing:
            raise SystemExit(f"unknown instance_id(s): {missing}")
    else:
        ids = eligible_ids()
        if args.limit is not None:
            random.Random(args.seed).shuffle(ids)
            ids = sorted(ids[:args.limit])

    if args.resume:
        before = len(ids)
        ids = [i for i in ids if not is_complete(i)]
        print(f"  resume: {before - len(ids)} already complete, {len(ids)} to run")

    workers = args.workers or rotation.suggested_workers()
    # `prune=True` is safe here and only here in the normal path: no worker has
    # started, so no pull is in flight to have its containerd lease pulled out
    # from under it.
    reclaimed = rotation.reconcile(leases, prune=True)
    # Measured AFTER the start-of-run reclaim, so a previous run's residue is
    # never charged to this one.
    baseline_free = rotation.free_bytes()
    if reclaimed["removed"]:
        progress.write(event="reclaimed_at_start", **reclaimed)

    print(f"M1 -- formcheck over SWE-bench Verified\n")
    print(f"  tasks      : {len(ids)}")
    print(f"  workers    : {workers}   "
          f"(disk-derived: {rotation.free_bytes() / 1024**3:.0f} GiB free, "
          f"~{rotation.ASSUMED_IMAGE_BYTES / 1024**3:.0f} GiB per image)")
    print(f"  timeout    : {args.timeout}s per task")
    print(f"  progress   : {PROGRESS}")
    if reclaimed["removed"]:
        print(f"  reclaimed  : {len(reclaimed['removed'])} stale image(s), "
              f"{reclaimed['reclaimed_bytes'] / 1024**3:.2f} GiB")
    print()

    progress.write(event="run_start", n_tasks=len(ids), workers=workers,
                   timeout=args.timeout, seed=args.seed, ids=ids)

    sem = asyncio.Semaphore(workers)
    done = 0

    async def guarded(instance):
        nonlocal done
        async with sem:
            record = await run_one(instance, leases, progress, args.timeout,
                                   baseline_free)
        done += 1
        flag = ("witness" if record["witnesses"]
                else "ok" if record["control"]["passed"] else "UNCHECKED")
        print(f"  [{done}/{len(ids)}] {record['instance_id']:40s} "
              f"{flag:9s} {record['elapsed_seconds']:7.1f}s")
        return record

    records = await asyncio.gather(*(guarded(instances[i]) for i in ids))
    progress.write(event="run_end", n_tasks=len(records))
    print(f"\n  {len(records)} record(s) -> {RESULTS}")
    print("  aggregate with: ~/.venv-fc/bin/python scale/aggregate.py")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
