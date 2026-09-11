"""On the 15 tasks that lose their entire graded suite, did any test run at all?

Static. No Docker. Reads the `graded_log` already recorded in
`scale/records_m4/` by the 500-task run, and the dataset's own F2P/P2P lists.

This is NOT the `import_local` measurement of `REPAIR.md` open item 1, which
needs 15 container runs. It answers the half of that question that the recorded
logs already settle:

  ran_none    the runner reported ZERO of the task's graded node ids. Nothing
              executed: the module did not import, so no test failed on its own
              terms and the entire suite loss is one import failure. The number
              of tests that would recover under `import_local` is
              `N - (tests naming the symbol)`, and the second term is >= 1 and
              not derivable from a log.
  ran_some    the runner reported some graded node ids, so tests executed and
              failed individually. The suite loss is not attributable to a
              module-import failure alone.

`ran_none` is a mechanism, not a fraction. It bounds the answer rather than
giving it: on a `ran_none` task at most `N - 1` tests can recover and at least
`N - 1` failures are collateral only if exactly one test names the symbol --
which is what the container measurement would establish and this cannot.

    ~/.venv-fc/bin/python repair/scan/allfail_mechanism.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "repro"))
RECORDS = os.path.join(ROOT, "scale", "records_m4")


def main():
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
    from datasets import load_dataset
    from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS
    from swebench.harness.log_parsers import MAP_REPO_TO_PARSER

    ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    by_id = {r["instance_id"]: r for r in ds}

    rows = []
    for name in sorted(os.listdir(RECORDS)):
        rec = json.load(open(os.path.join(RECORDS, name), encoding="utf-8"))
        for w in rec.get("witnesses") or []:
            g = w["graded_report"]
            if g["f2p_pass"] or g["p2p_pass"]:
                continue                      # not an all-fail witness
            inst = by_id[rec["instance_id"]]
            graded = json.loads(inst["FAIL_TO_PASS"]) + json.loads(inst["PASS_TO_PASS"])
            cmd = MAP_REPO_VERSION_TO_SPECS[rec["repo"]][inst["version"]]["test_cmd"]
            if isinstance(cmd, list):
                cmd = cmd[-1]
            log = w["graded_log"] or ""
            sm = MAP_REPO_TO_PARSER[rec["repo"]](log.split(cmd)[-1], None)
            present = [t for t in graded if t in sm]
            rows.append({
                "task": rec["instance_id"], "repo": rec["repo"],
                "symbol": w["anchor"], "n_graded": len(graded),
                "n_reported": len(present),
                "mechanism": "ran_none" if not present else "ran_some",
                "n_status_entries": len(sm),
            })
    return rows


if __name__ == "__main__":
    rows = main()
    print(f"{len(rows)} all-fail witness rows across "
          f"{len({r['task'] for r in rows})} tasks\n")
    print(f"{'task':34s} {'symbol':22s} {'runner reported':>16s} {'graded':>7s}  mechanism")
    for r in sorted(rows, key=lambda x: x["task"]):
        print(f"{r['task']:34s} {r['symbol']:22s} {r['n_reported']:16d} "
              f"{r['n_graded']:7d}  {r['mechanism']}")
    # Deduplicate by TASK before summing: `pylint-4551` and `sphinx-7590` each
    # carry two witness symbols over the same suite, and summing rows would count
    # their graded tests twice.
    per_task = {}
    for r in rows:
        per_task.setdefault(r["task"], r)
    none_tasks = [t for t, r in per_task.items() if r["mechanism"] == "ran_none"]
    total = sum(per_task[t]["n_graded"] for t in none_tasks)
    print(f"\nran_none : {len(none_tasks)} of {len(per_task)} tasks -- "
          f"{total} graded tests across them, none executed")
    print(f"ran_some : {len(per_task) - len(none_tasks)} tasks")
    json.dump(rows, open(os.path.join(HERE, "allfail_mechanism.json"), "w"),
              indent=2)
