"""M0 -- one task, in its own image, through the real `validate` path.

This calls `verifiers.v1.cli.validate._run_check(task, cfg, "formcheck")`. That
function provisions the runtime, starts the container, runs `Task.setup`,
dispatches to the patched hook and classifies with the untouched `_classify`.
The row printed is the row `validate` would persist to `results.jsonl`.

What is real here that was not real in Phase 3: the runtime is `DockerRuntime`
and the image is the task's own epoch-pinned one, resolved through
`resolve_runtime_config`, which injects `task.data.image` exactly as it does for
a Harbor task. Phase 3 had to say "the runtime is subprocess, not a container".
That caveat is gone.

Usage (inside WSL, with ~/.venv-fc):
    ~/.venv-fc/bin/python scale/m0_run.py [--keep-image]
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "repro"))

import verifiers.v1 as vf  # noqa: E402
from verifiers.v1.cli.validate import _run_check, validation_mode  # noqa: E402
from verifiers.v1.configs.cli.validate import ValidateConfig  # noqa: E402
from verifiers.v1.runtimes import DockerConfig  # noqa: E402

import diff_verdicts  # noqa: E402
import oracle as oracle_mod  # noqa: E402
from container_task import (  # noqa: E402
    ContainerData, ContainerFormcheckTask, MarkerSetOracle,
)
from images import image_ref  # noqa: E402

INSTANCE = "pytest-dev__pytest-10356"
REPRO = os.path.join(ROOT, "repro")
RESULTS = os.path.join(ROOT, "scale", "results")


def read(name):
    with open(os.path.join(REPRO, name), encoding="utf-8") as f:
        return f.read()


def disk_used():
    """Docker's own accounting, in bytes -- images + containers + volumes."""
    out = subprocess.run(
        ["docker", "system", "df", "--format", "{{.Type}}\t{{.Size}}"],
        capture_output=True, text=True).stdout.strip()
    return out or "(unavailable)"


def build_spec():
    meta = json.loads(read("meta.json"))
    return {
        "instance_id": INSTANCE,
        "meta": meta,
        "gold_diff": read("gold.diff"),
        "tests_diff": read("tests.diff"),
        "issue": read("issue.txt"),
        # The file the reference solution changes, and the production tree the
        # dynamic-reach precondition must be able to see.
        "target": "src/_pytest/mark/structures.py",
        "scan_root": "src",
        "test_files": ["testing/test_mark.py"],
        # Anchors are restricted to symbols the GOLD PATCH itself touches.
        # Without that, `symbol_rename` would sweep every definition in the
        # module and picking the ones that produce a witness would be selecting
        # for the outcome. This is the same set Phase 2 used.
        "in_scope": {"get_unpacked_marks", "normalize_mark_list", "store_mark",
                     "MarkDecorator"},
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-image", action="store_true",
                    help="skip the `docker rmi` at the end (debugging only)")
    args = ap.parse_args()

    image = image_ref(INSTANCE)
    spec = build_spec()

    print("M0 -- formcheck inside the task's own epoch-pinned image\n")
    print(f"  instance   : {INSTANCE}")
    print(f"  image      : {image}")
    print(f"  verifiers  : {vf.__name__} @ 04b0bf5 + verifiers-formcheck.patch")

    t0 = time.time()
    pull = subprocess.run(["docker", "pull", image], capture_output=True, text=True)
    if pull.returncode != 0:
        print(f"\n  docker pull FAILED: {pull.stderr.strip()[:400]}")
        return 1
    print(f"  pull       : {round(time.time() - t0, 1)}s")
    print(f"  disk after pull:\n    " + disk_used().replace("\n", "\n    "))

    cfg = ValidateConfig(taskset={"id": "harbor"}, runtime=DockerConfig(),
                         only_formcheck=True)
    print(f"  mode       : {validation_mode(cfg)!r}"
          "   (alongside 'gold' | 'setup' | 'all')\n")

    data = ContainerData(idx=0, name=INSTANCE, prompt="",
                         image=image, workdir="/testbed")
    oracle = MarkerSetOracle(oracle_mod.REPRO, oracle_mod.CONFTEST, {"foo", "bar"})
    task = ContainerFormcheckTask(data, spec, oracle)

    t0 = time.time()
    row = await _run_check(task, cfg, "formcheck")
    elapsed = round(time.time() - t0, 1)

    log = getattr(task, "formcheck_log", [])
    print("  transform log (as the hook saw it):")
    for label, verdict, why in log:
        print(f"    {verdict:15s} {label:52s} {why}")

    print("\n  results.jsonl row that `validate` would persist:")
    for key in ("index", "name", "mode", "valid", "reason", "elapsed", "error"):
        print(f"    {key:9s} = {row.get(key)!r}")

    comparison = diff_verdicts.compare(
        os.path.join(REPRO, "f2_verdicts.json"), log)
    print("\n" + "=" * 96)
    print("FIELD-BY-FIELD DIFF vs Phase 2")
    print(comparison["table"])

    control = next((w for lbl, _, w in log if lbl == "<control>"), None)
    judged = sum(1 for _, v, _ in log if v in ("WITNESS", "CLEAN", "INVALID"))
    invalid = sum(1 for _, v, _ in log if v == "INVALID")
    print(f"  control: {control}")
    print(f"  judged : {judged}   invalid: {invalid}")

    os.makedirs(RESULTS, exist_ok=True)
    out = {
        "instance_id": INSTANCE,
        "image": image,
        "row": row,
        "log": log,
        "judged": judged,
        "invalid": invalid,
        "elapsed_seconds": elapsed,
        "comparison": {k: v for k, v in comparison.items() if k != "table"},
    }
    path = os.path.join(RESULTS, f"{INSTANCE}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=2)
    print(f"\n  -> {path}")

    if not args.keep_image:
        subprocess.run(["docker", "rmi", "-f", image], capture_output=True)
        print(f"  disk after rmi:\n    " + disk_used().replace("\n", "\n    "))
    return 0 if comparison["identical"] else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
