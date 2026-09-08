"""Which SWE-bench Verified tasks formcheck can check at all, from the patches.

NAMED `eligibility`, NOT `select`: a module named `select.py` on `sys.path`
shadows the stdlib `select` that asyncio's event loop imports, and the whole
run is asyncio.

No container starts here, and none needs to: every input is a string in the
dataset. That is the point. Anchor availability bounds coverage from inside a
task (`writeup.md` 6.5); the shape of the gold patch bounds it from outside, and
this pass measures that bound for all 500 tasks in seconds rather than inferring
it from whichever subset a run happened to reach.

TWO FRACTIONS, AND WHY BOTH ARE REPORTED.

`single_file` is the pre-M1 ceiling. The hook was single-target: one
`FORMCHECK_TARGET`, and `Operator.anchors`/`apply` searched and rewrote that one
file, while the in-scope filter was "a symbol the gold patch touches". On a task
whose gold patch spans two files those two disagree, and the failure is worse
than under-coverage -- the run emits a `NOT_APPLICABLE` row whose stated reason
("no anchor inside the gold-touched region") is FALSE (`CHANGES.md` 4).

`eligible` is the ceiling after M1 widened `FORMCHECK_TARGETS` to the tuple of
gold-touched sources. Both are reported because the difference between them is
exactly what the widening bought, and a single number would hide it.

A task with no production Python file in its gold patch is ineligible under
either rule: the transforms rewrite the SOLUTION, and there is nothing to
rewrite. That is a real exclusion, counted and named, not a silent skip.

Usage:
    ~/.venv-fc/bin/python scale/eligibility.py [-o scale/eligible.jsonl]
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DATASET = "princeton-nlp/SWE-bench_Verified"
SPLIT = "test"

# Same tuple the hook's tree scan excludes, for the same reason: a transform
# rewrites the solution, never the graded tests. A gold patch that touches only
# a test tree leaves the hook nothing to work on.
TEST_HINTS = ("test", "tests", "testing", "doc", "docs")

_DIFF_GIT = re.compile(r"^diff --git a/(.+?) b/(.+)$", re.M)


def patched_files(patch: str) -> list[str]:
    """Every path a unified diff touches, in order, deduplicated.

    Read from the `diff --git` headers rather than from `+++`/`---`, because a
    deletion writes `+++ /dev/null` and a creation writes `--- /dev/null`, and
    both still name the real path in the header. The b-side is authoritative
    except for a pure delete, where it is the a-side that exists in the tree the
    transform would run against.
    """
    out: list[str] = []
    for a, b in _DIFF_GIT.findall(patch):
        path = a if b == "/dev/null" else b
        if path not in out:
            out.append(path)
    return out


def is_production_python(path: str) -> bool:
    """A `.py` the hook could actually rewrite: not a test, not a doc."""
    if not path.endswith(".py"):
        return False
    parts = [p.lower() for p in path.split("/")]
    if any(p in TEST_HINTS or p.startswith(".") for p in parts[:-1]):
        return False
    leaf = parts[-1]
    return not (leaf.startswith("test_") or leaf.endswith("_test.py")
                or leaf == "conftest.py")


def classify(instance: dict) -> dict:
    files = patched_files(instance["patch"])
    targets = [f for f in files if is_production_python(f)]
    return {
        "instance_id": instance["instance_id"],
        "repo": instance["repo"],
        "base_commit": instance["base_commit"],
        "files_touched": files,
        "n_files": len(files),
        "targets": targets,
        "n_targets": len(targets),
        # The pre-M1 rule, kept so the widening's effect stays measurable.
        "single_file": len(files) == 1,
        # The post-M1 rule: the hook needs at least one source it can rewrite.
        "eligible": len(targets) >= 1,
        "n_fail_to_pass": len(json.loads(instance["FAIL_TO_PASS"])),
        "n_pass_to_pass": len(json.loads(instance["PASS_TO_PASS"])),
    }


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    single = sum(1 for r in rows if r["single_file"])
    eligible = sum(1 for r in rows if r["eligible"])
    single_target = sum(1 for r in rows if r["n_targets"] == 1)
    hist: dict[int, int] = {}
    for r in rows:
        hist[r["n_targets"]] = hist.get(r["n_targets"], 0) + 1
    return {
        "dataset": DATASET,
        "n_tasks": n,
        "single_file": single,
        "single_file_fraction": round(single / n, 4) if n else None,
        "single_target": single_target,
        "single_target_fraction": round(single_target / n, 4) if n else None,
        "eligible": eligible,
        "eligible_fraction": round(eligible / n, 4) if n else None,
        "ineligible_no_production_python": n - eligible,
        "targets_histogram": {str(k): hist[k] for k in sorted(hist)},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "eligible.jsonl"))
    ap.add_argument("--summary", default=os.path.join(HERE, "eligible_summary.json"))
    args = ap.parse_args()

    from datasets import load_dataset  # imported late: this is the slow import

    ds = load_dataset(DATASET, split=SPLIT)
    rows = [classify(inst) for inst in ds]
    rows.sort(key=lambda r: r["instance_id"])

    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    summary = summarize(rows)
    with open(args.summary, "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, indent=2, sort_keys=True)

    n = summary["n_tasks"]
    print(f"{DATASET} ({SPLIT}) -- {n} tasks, no container started\n")
    print("  Gold patches touching exactly one file (the PRE-M1 ceiling):")
    print(f"    {summary['single_file']}/{n} = "
          f"{summary['single_file_fraction']:.1%}")
    print("\n  Gold patches with >=1 production Python file (the POST-M1 rule):")
    print(f"    {summary['eligible']}/{n} = {summary['eligible_fraction']:.1%}")
    print(f"    excluded, no production Python in the gold patch: "
          f"{summary['ineligible_no_production_python']}")
    print("\n  Production Python files per gold patch:")
    for k, v in summary["targets_histogram"].items():
        bar = "#" * round(60 * v / n)
        print(f"    {k:>3} target(s)  {v:>4}  {v / n:6.1%}  {bar}")
    print(f"\n  -> {args.out}\n  -> {args.summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
