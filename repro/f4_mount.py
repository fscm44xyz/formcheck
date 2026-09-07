"""Phase 4.2 -- mount SWE-bench Verified tasks locally, no Docker.

One directory per task under `primein/f4/<instance_id>/`: a clone at the base
commit and a venv with the repo installed editable. Deliberately time-boxed --
if a task does not mount in one straightforward attempt it is recorded as NOT
MOUNTABLE with the reason and we move on. The mount rate is a reported number,
not a failure.

Repos are chosen for being pure Python with no native build step. astropy,
matplotlib and scikit-learn are excluded on that basis; sympy (`bin/test`),
sphinx (`tox`) and django (`./tests/runtests.py`) are excluded because their
graded command is not plain pytest and the log parser expects that shape.

Run under .venv (needs pandas + swebench for the specs).
"""
import os
import re
import sys
import json
import time
import shutil
import argparse
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import swebench_shim  # noqa: F401,E402
from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
F4 = os.path.join(ROOT, "f4")
STATE = os.path.join(F4, "mounts.json")
TIMEOUT_CLONE = 900
TIMEOUT_INSTALL = 1200


def sh(argv, cwd=None, timeout=600, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, env=e)


def load_state():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    os.makedirs(F4, exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def mount(row, python="python"):
    """Clone + venv + editable install. Returns a record; never raises."""
    iid = row["instance_id"]
    base = os.path.join(F4, iid)
    rec = {"instance_id": iid, "repo": row["repo"], "version": row["version"],
           "dir": base, "mounted": False, "reason": None, "seconds": None}
    t0 = time.time()
    try:
        repo_dir = os.path.join(base, "repo")
        venv = os.path.join(base, ".venv")
        if os.path.isdir(base):
            shutil.rmtree(base, ignore_errors=True)
        os.makedirs(base, exist_ok=True)

        r = sh(["git", "clone", "-q", f"https://github.com/{row['repo']}.git",
                repo_dir], timeout=TIMEOUT_CLONE)
        if r.returncode != 0:
            rec["reason"] = f"clone failed: {r.stderr.strip()[:200]}"
            return rec
        r = sh(["git", "checkout", "-q", row["base_commit"]], cwd=repo_dir)
        if r.returncode != 0:
            rec["reason"] = f"checkout failed: {r.stderr.strip()[:200]}"
            return rec

        r = sh([python, "-m", "venv", venv], timeout=600)
        if r.returncode != 0:
            rec["reason"] = f"venv failed: {r.stderr.strip()[:200]}"
            return rec
        py = os.path.join(venv, "Scripts", "python.exe")
        if not os.path.exists(py):
            py = os.path.join(venv, "bin", "python")
        rec["python"] = py

        spec = MAP_REPO_VERSION_TO_SPECS.get(row["repo"], {}).get(row["version"], {})
        rec["test_cmd"] = (spec.get("test_cmd")[-1]
                           if isinstance(spec.get("test_cmd"), list)
                           else spec.get("test_cmd"))
        # pytest first: the graded command is pytest for every repo we attempt.
        r = sh([py, "-m", "pip", "install", "-q", "pytest"], timeout=TIMEOUT_INSTALL)
        if r.returncode != 0:
            rec["reason"] = f"pytest install failed: {r.stderr.strip()[:200]}"
            return rec
        r = sh([py, "-m", "pip", "install", "-q", "-e", "."], cwd=repo_dir,
               timeout=TIMEOUT_INSTALL)
        if r.returncode != 0:
            tail = (r.stderr or r.stdout).strip().splitlines()
            rec["reason"] = "editable install failed: " + " | ".join(tail[-3:])[:300]
            return rec

        pkg = spec.get("packages")
        if pkg and pkg not in ("requirements.txt", "environment.yml"):
            sh([py, "-m", "pip", "install", "-q", *pkg.split()],
               timeout=TIMEOUT_INSTALL)

        r = sh([py, "-c", "import pytest, sys; sys.stdout.write(pytest.__version__)"])
        if r.returncode != 0:
            rec["reason"] = f"pytest unusable: {r.stderr.strip()[:200]}"
            return rec
        rec["pytest"] = r.stdout.strip()
        rec["mounted"] = True
        return rec
    except subprocess.TimeoutExpired as e:
        rec["reason"] = f"timeout after {e.timeout}s in {e.cmd[0] if e.cmd else '?'}"
        return rec
    except Exception as e:  # noqa: BLE001 - a mount failure is data, not a crash
        rec["reason"] = f"{type(e).__name__}: {e}"[:300]
        return rec
    finally:
        rec["seconds"] = round(time.time() - t0, 1)


def write_task_files(row, rec):
    """gold.diff / tests.diff / meta.json / issue.txt beside the clone."""
    base = rec["dir"]
    with open(os.path.join(base, "gold.diff"), "w", encoding="utf-8", newline="\n") as f:
        f.write(row["patch"])
    with open(os.path.join(base, "tests.diff"), "w", encoding="utf-8", newline="\n") as f:
        f.write(row["test_patch"])
    with open(os.path.join(base, "issue.txt"), "w", encoding="utf-8") as f:
        f.write(row["problem_statement"])
    meta = {"instance_id": row["instance_id"], "repo": row["repo"],
            "version": row["version"], "base_commit": row["base_commit"],
            "FAIL_TO_PASS": row["FAIL_TO_PASS"], "PASS_TO_PASS": row["PASS_TO_PASS"]}
    with open(os.path.join(base, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("instances", nargs="+")
    ap.add_argument("--parquet", required=True)
    args = ap.parse_args()

    import pandas as pd
    df = pd.read_parquet(args.parquet).set_index("instance_id", drop=False)
    state = load_state()
    for iid in args.instances:
        if iid not in df.index:
            print(f"  {iid:34s} NOT IN DATASET")
            continue
        row = df.loc[iid].to_dict()
        for key in ("FAIL_TO_PASS", "PASS_TO_PASS"):
            v = row[key]
            row[key] = list(v) if not isinstance(v, str) else json.loads(v)
        print(f"  mounting {iid} ...", flush=True)
        rec = mount(row)
        if rec["mounted"]:
            write_task_files(row, rec)
            print(f"    MOUNTED   {rec['seconds']}s  pytest {rec.get('pytest')}")
        else:
            print(f"    NOT MOUNTABLE ({rec['seconds']}s): {rec['reason']}")
            shutil.rmtree(rec["dir"], ignore_errors=True)
        state[iid] = rec
        save_state(state)
    ok = sum(1 for r in state.values() if r["mounted"])
    print(f"\n  mount rate: {ok}/{len(state)}")


if __name__ == "__main__":
    main()
