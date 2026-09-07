"""M4 execution worker (.venv-pytest). Handles both M1 solutions and held-out
mutants (apply gold.diff, then a mechanical string transform). Writes
log_m4_<name>.txt. Reuses run_case + m1_run so M1 solutions stay byte-identical.
"""
import os, sys, subprocess
sys.path.insert(0, os.path.dirname(__file__))
import run_case, m1_run
from m4_mutants import HELDOUT

M1_NAMES = {"gold", "alt", "bug_none", "bug_direct", "bug_first", "bug_dropown"}

def apply_heldout(name):
    m = HELDOUT[name]
    assert m["base"] == "gold", "only gold-based held-out mutants supported"
    run_case.apply_patch(os.path.join(run_case.HERE, "gold.diff"))
    with open(run_case.STRUCT, encoding="utf-8") as f:
        src = f.read()
    if m["old"] not in src:
        raise RuntimeError(f"held-out anchor missing for {name}: {m['old']!r}")
    src = src.replace(m["old"], m["new"], 1)
    with open(run_case.STRUCT, "w", encoding="utf-8") as f:
        f.write(src)

def run_one(name):
    run_case.restore()
    run_case.apply_patch(os.path.join(run_case.HERE, "tests.diff"))
    m1_run.apply_repaired_test()
    if name in M1_NAMES:
        m1_run.apply_solution(name)
    elif name in HELDOUT:
        apply_heldout(name)
    else:
        raise SystemExit("unknown solution " + name)
    run = subprocess.run(
        [run_case.PY, "-m", "pytest", "-rA", "-p", "no:cacheprovider", "testing/test_mark.py"],
        cwd=run_case.REPO, capture_output=True, text=True, timeout=600,
    )
    log = "+ pytest -rA testing/test_mark.py\n" + run.stdout + "\n" + run.stderr
    with open(os.path.join(run_case.HERE, f"log_m4_{name}.txt"), "w", encoding="utf-8") as f:
        f.write(log)
    run_case.restore()
    tail = [l for l in run.stdout.splitlines() if "passed" in l or "failed" in l or "error" in l]
    print(f"[{name:12s}] exit={run.returncode}  {tail[-1] if tail else '?'}")

if __name__ == "__main__":
    run_case.assert_editable_pytest()
    for n in sys.argv[1:]:
        run_one(n)
