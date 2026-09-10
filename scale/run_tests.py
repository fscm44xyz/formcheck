"""Run every fast test. No docker, no network, about a second.

One file per defect class that has actually cost a run:

    test_scope.py      the gold-patch scope rule            (CHANGES.md 5, 6)
    test_rotation.py   leases, reconcile, prune, budget     (CHANGES.md 10-12)
    test_partition.py  the writeup.md 6.2 P2P partition     (CHANGES.md 13)
    test_digest.py     the graded-memo digest               (CHANGES.md 16, D2)
    test_aggregate.py  the no-merged-rate guards, Wilson    (CHANGES.md 2)
    ../repair/test_repair_m0a.py
                       the persisted transform + the overlay's
                       production-file assertion                (repair-M0a)
    ../repair/test_repair_m0b.py
                       the repair's two conditions: coupling gone,
                       broken code still rejected                  (repair-M0b)
    ../repair/test_repair_m0c.py
                       the import shape, and how much of its blast
                       radius was one import line                  (repair-M0c)

Deliberately NOT covered here, because they need a container: the M0 gate
(`scale/m0_run.py`, a 3.8 GB pull) and anything exercising a real image. Those
remain the slow gates; this is the one that can run on every change.

    ~/.venv-fc/bin/python scale/run_tests.py
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# Paths are relative to this file. `repair/` is listed here rather than left to
# be run by hand: a test suite nothing invokes is the silent-omission defect of
# CHANGES.md 19, one directory up.
SUITES = ["test_scope.py", "test_rotation.py", "test_partition.py",
          "test_digest.py", "test_aggregate.py", "test_burn.py",
          "test_guards_fire.py",
          os.path.join("..", "repair", "test_repair_m0a.py"),
          os.path.join("..", "repair", "test_repair_m0b.py"),
          os.path.join("..", "repair", "test_repair_m0c.py")]


def main():
    failed, total, passed = [], 0, 0
    for name in SUITES:
        r = subprocess.run([sys.executable, os.path.join(HERE, name)],
                           capture_output=True, text=True)
        tail = [ln for ln in r.stdout.splitlines() if "passed" in ln]
        summary = tail[-1].strip() if tail else "(no summary)"
        if "/" in summary:
            got, _, tot = summary.split()[0].partition("/")
            passed += int(got)
            total += int(tot)
        print(f"  {name:28s} {summary}")
        if r.returncode != 0:
            failed.append(name)
            for ln in r.stdout.splitlines():
                if ln.startswith("  FAIL"):
                    print(f"      {ln.strip()}")
    print(f"\n{passed}/{total} across {len(SUITES)} suites")
    if failed:
        print(f"FAILING: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
