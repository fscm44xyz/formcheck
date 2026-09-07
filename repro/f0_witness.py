"""Phase 0 -- the falsifiable question, executed.

Can a MECHANICAL, behaviour-preserving transform of the gold patch reproduce the
witness we wrote by hand in July?

For pytest-10356 the gold patch invents a keyword-only parameter
`get_unpacked_marks(obj, *, consider_mro=True)` that the issue (#7792) never
mentions, and the graded test asserts on it. `f0_equiv.kwonly_specialize`
specialises that parameter away. If the result

  (a) still satisfies the issue's observable contract  -> oracle: BOTH markers
  (b) fails the graded test                            -> reward 0.0

then the graded reward is coupled to the fix's form, and the witness is
mechanical rather than hand-written.

Runs under .venv-pytest (runs the tests). Grading is done by f0_gate.py under
.venv. Writes log_f0_witness.txt and f0_transform.diff.
"""
import os
import sys
import json
import shutil
import difflib
import tempfile
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_case
import oracle
from f0_equiv import kwonly_specialize, Refused

HERE = run_case.HERE
PYTHON_PY = os.path.join(run_case.REPO, "src", "_pytest", "python.py")
ISSUE = os.path.join(HERE, "issue.txt")
FUNC, PARAM = "get_unpacked_marks", "consider_mro"


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def apply_transform():
    """Apply gold, then the equivalence-preserving transform. Returns the report
    and the unified diff of the transform itself (gold -> transformed)."""
    run_case.apply_patch(os.path.join(HERE, "gold.diff"))
    before = _read(run_case.STRUCT)
    after, report = kwonly_specialize(
        before, FUNC, PARAM, _read(ISSUE),
        extra_sources={"src/_pytest/python.py": _read(PYTHON_PY)},
    )
    with open(run_case.STRUCT, "w", encoding="utf-8") as f:
        f.write(after)
    diff = "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile="a/src/_pytest/mark/structures.py (gold)",
        tofile="b/src/_pytest/mark/structures.py (gold + kwonly_specialize)",
    ))
    return report, diff


def reset():
    run_case.restore()


def graded_run():
    """(b) the transformed gold against the ORIGINAL inherited graded test."""
    reset()
    run_case.apply_patch(os.path.join(HERE, "tests.diff"))
    report, diff = apply_transform()
    run = subprocess.run(
        [run_case.PY, "-m", "pytest", "-rA", "-p", "no:cacheprovider", run_case.TEST_FILE],
        cwd=run_case.REPO, capture_output=True, text=True, timeout=600,
    )
    log = run_case.TEST_CMD_ECHO + "\n" + run.stdout + "\n" + run.stderr
    with open(os.path.join(HERE, "log_f0_witness.txt"), "w", encoding="utf-8") as f:
        f.write(log)
    with open(os.path.join(HERE, "f0_transform.diff"), "w", encoding="utf-8") as f:
        f.write(diff)
    reset()
    return report, log


def oracle_run():
    """(a) the transformed gold against the issue's observable contract."""
    reset()
    apply_transform()
    proj = tempfile.mkdtemp(prefix="f0_oracle_")
    try:
        with open(os.path.join(proj, "test_repro.py"), "w") as f:
            f.write(oracle.REPRO)
        with open(os.path.join(proj, "conftest.py"), "w") as f:
            f.write(oracle.CONFTEST)
        subprocess.run([run_case.PY, "-m", "pytest", "-p", "no:cacheprovider", "-q",
                        "--no-header", "-o", "addopts=", proj],
                       cwd=proj, capture_output=True, text=True, timeout=300)
        mpath = os.path.join(proj, "markers.txt")
        markers = _read(mpath).split(",") if os.path.exists(mpath) else []
        markers = sorted(m for m in markers if m)
    finally:
        shutil.rmtree(proj, ignore_errors=True)
        reset()
    return markers


def main():
    run_case.assert_editable_pytest()
    print("Phase 0 -- mechanical witness by equivalence-preserving transform\n")
    try:
        report, log = graded_run()
    except Refused as e:
        print(f"REFUSED: {e}")
        print("\nThe operator declined to transform. Phase 0 cannot proceed on "
              "this task with this operator.")
        raise SystemExit(2)

    print("operator :", report["operator"])
    print("target   :", f"{report['function']}(*, {report['parameter']}=...)")
    print("confidence:", report["confidence"])
    for k, v in report["preconditions"].items():
        print(f"  {k:16s} {v}")
    print(f"  {'rewrites':16s} {report['call_sites_rewritten']} call site(s); "
          f"siblings emitted: {report['siblings_emitted']}")

    markers = oracle_run()
    tail = [l for l in log.splitlines() if " passed" in l or " failed" in l]
    print("\n(a) ORACLE  (issue contract, public iter_markers):")
    print(f"      test_dings markers = {markers}  ->",
          "BOTH markers: contract satisfied" if set(markers) == {"foo", "bar"}
          else "CONTRACT BROKEN -- transform is NOT behaviour-preserving")
    print("\n(b) GRADED  (original inherited test):")
    print(f"      {tail[-1] if tail else '?'}")
    print("      log_f0_witness.txt written; grade it with f0_gate.py under .venv")

    json.dump({"report": report, "oracle_markers": markers},
              open(os.path.join(HERE, "f0_result.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
