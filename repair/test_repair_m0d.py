"""repair-M0d: `django__django-11179`. Django's runner, and a repair NOT shipped.

Three things are pinned here, and the third is the point:

  1. the positive control works under django's `runtests.py` -- a landed overlay
     is distinguishable from a dropped one;
  2. under the rename the graded node ids are ABSENT from the status map, which
     `test_failed` scores identically to "ran and failed";
  3. the candidate repair passes BOTH conditions and is still a hollowing-out.
     `bug_nofast` is caught by the original test's precondition assertion and not
     by the repaired test; the task-level reward is 0.0 either way because other
     P2P tests cover it.

(3) is asserted as an EXPECTED, RECORDED finding. If a future change makes the
repaired test catch `bug_nofast` again, these tests fail and someone has to look
-- which is the point of pinning a negative result rather than writing it in
prose only.

Regenerate with:

    ~/.venv-fc/bin/python repair/m0d_gate.py
    ~/.venv-fc/bin/python scale/run.py --instance-id django__django-11179 \
        --records-dir repair/records_m0d/plain
    ~/.venv-fc/bin/python scale/run.py --instance-id django__django-11179 \
        --tests-overlay repair/overlay_positive_django_11179.diff \
        --records-dir repair/records_m0d/positive
    ~/.venv-fc/bin/python scale/run.py --instance-id django__django-11179 \
        --tests-overlay repair/overlay_repair_django_11179.diff \
        --records-dir repair/records_m0d/repaired

    ~/.venv-fc/bin/python repair/test_repair_m0d.py
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "repro"))

GATE = os.path.join(HERE, "m0d_gate_result.json")
RECORDS = os.path.join(HERE, "records_m0d")
INSTANCE = "django__django-11179.json"

SYMBOL = "Collector"
MUTANTS = ("bug_revert", "bug_zero", "bug_nofast")
VARIANTS = ("original", "import_local", "repaired")
TARGETED = "test_fast_delete_fk (delete.tests.FastDeleteTests)"
F2P = "test_fast_delete_instance_set_pk_none (delete.tests.FastDeleteTests)"


def _load(path, what):
    assert os.path.exists(path), (
        f"missing {what}: {path} -- regenerate it with the command in this "
        "file's header. A missing artifact must FAIL, not skip.")
    with open(path, encoding="utf-8") as f:
        return json.load(f) if path.endswith(".json") else f.read()


def _record(name):
    return _load(os.path.join(RECORDS, name, INSTANCE), f"{name} record")


# --- 1. the control works under this runner ---------------------------------

def test_positive_control_works_under_djangos_runner():
    """The unknown this milestone existed to settle first."""
    control = _record("positive")["control"]
    assert control["passed"] is False, control
    log = control["log"] or ""
    assert "AssertionError: overlay landed" in log, (
        "a landed overlay is NOT distinguishable from a dropped one under "
        "django's runner -- everything downstream is unsafe")
    assert control["graded"]["p2p_failing"] == [TARGETED], control["graded"]
    assert control["graded"]["f2p_fail"] == 0, control["graded"]
    assert control["graded"]["p2p_fail"] == 1, control["graded"]


# --- 2. absence is scored as failure ----------------------------------------

def test_absence_is_scored_identically_to_failure():
    """`test_failed` is `case not in sm or sm[case] in [FAILED, ERROR]`.

    Not a claim about django: one expression, both branches, every repo. Asserted
    against the real `swebench` function rather than restated.
    """
    from swebench.harness.grading import test_failed
    case = F2P
    assert test_failed(case, {}) is True
    assert test_failed(case, {case: "FAILED"}) is True
    assert test_failed(case, {case: "PASSED"}) is False


def test_the_rename_leaves_no_graded_node_id_in_the_status_map():
    """Under the rename django reports one synthetic `_FailedTest` and nothing
    else, so all 41 graded ids are absent -- and the log, unlike the reward,
    says so."""
    gate = _load(GATE, "gate result")
    r = gate["original/gold_renamed"]
    assert r["graded_ids_present"] == 0, r
    assert (r["f2p_pass"], r["p2p_pass"]) == (0, 0), r
    assert r["names_symbol_in_log"] is True, (
        "the log must still name the symbol -- that is how attribution "
        "distinguishes what the reward cannot")


# --- 3. the split, and the drift -------------------------------------------

def test_the_blast_radius_was_almost_entirely_the_import_line():
    """Candidate pattern 2 at n=2: 40 of 41 failures were one import line."""
    gate = _load(GATE, "gate result")
    orig, local = gate["original/gold_renamed"], gate["import_local/gold_renamed"]
    assert (orig["f2p_pass"], orig["p2p_pass"]) == (0, 0), orig
    assert (local["f2p_pass"], local["f2p_fail"]) == (0, 1), local
    assert (local["p2p_pass"], local["p2p_fail"]) == (40, 0), local
    assert local["reward"] == 0.0, local


def test_both_conditions_pass():
    """Recorded because the point is that passing them is not sufficient."""
    gate = _load(GATE, "gate result")
    assert gate["repaired/gold_renamed"]["reward"] == 1.0, gate["repaired/gold_renamed"]
    assert gate["repaired/gold"]["reward"] == 1.0, gate["repaired/gold"]
    for name in MUTANTS:
        assert gate[f"repaired/{name}"]["reward"] == 0.0, name


def test_the_repair_is_a_hollowing_out_that_c2_cannot_see():
    """THE FINDING. `bug_nofast` disables the fast path -- the regression the
    deleted precondition existed to catch.

    Original test: the F2P test FAILS (0/1). Repaired test: it PASSES (1/1),
    because the slow path nulls the pk too. The task reward is 0.0 either way,
    because ten other P2P tests catch it -- so C2 reads CAUGHT while the repaired
    test detects nothing.
    """
    gate = _load(GATE, "gate result")
    orig, rep = gate["original/bug_nofast"], gate["repaired/bug_nofast"]
    assert orig["f2p_pass"] == 0 and orig["f2p_fail"] == 1, orig
    assert rep["f2p_pass"] == 1 and rep["f2p_fail"] == 0, (
        "the repaired test now catches bug_nofast -- the recorded finding no "
        "longer holds and M0D_RESULT.md must be revisited")
    assert orig["reward"] == rep["reward"] == 0.0, (orig["reward"], rep["reward"])
    assert orig["p2p_fail"] == rep["p2p_fail"] == 10, (
        "the suite-level catch came from other P2P tests; if that changed, the "
        "explanation in M0D_RESULT.md changed too")


def test_the_other_mutants_show_no_drift():
    """Only `bug_nofast` drifts -- the repair did not weaken anything else."""
    gate = _load(GATE, "gate result")
    for name in ("bug_revert", "bug_zero"):
        o, r = gate[f"original/{name}"], gate[f"repaired/{name}"]
        assert (o["f2p_pass"], o["f2p_fail"]) == (r["f2p_pass"], r["f2p_fail"]), \
            (name, o, r)


def test_every_mutant_actually_ran_the_graded_suite():
    """The guard that django made necessary: a 0.0 with no graded ids reported
    is absence, not detection."""
    gate = _load(GATE, "gate result")
    baseline = gate["repaired/gold"]["graded_ids_present"]
    assert baseline == 41, baseline
    for variant in VARIANTS:
        for name in MUTANTS:
            got = gate[f"{variant}/{name}"]["graded_ids_present"]
            assert got == baseline, (
                f"{variant}/{name} reported {got}/{baseline} graded node ids -- "
                "its 0.0 would be absence, not detection")


def test_the_mutants_are_behavioural_not_coupled():
    gate = _load(GATE, "gate result")
    for variant in VARIANTS:
        for name in MUTANTS:
            assert gate[f"{variant}/{name}"]["names_symbol_in_log"] is False, \
                f"{variant}/{name} fails by naming {SYMBOL}"


# --- formcheck's verdict, and its blind spot --------------------------------

def test_formcheck_reports_clean_on_a_repair_that_was_not_shipped():
    """formcheck cannot see the hollowing-out either: WITNESS -> CLEAN."""
    before, after = _record("plain"), _record("repaired")
    assert [w["anchor"] for w in before["witnesses"]] == [SYMBOL], before["witnesses"]
    assert after["witnesses"] == [], after["witnesses"]
    verdicts = {label: verdict for label, verdict, _ in after["log"]}
    assert verdicts[f"symbol_rename:{SYMBOL}"] == "CLEAN", verdicts


def test_the_clean_is_not_a_stale_memo():
    trace = _record("repaired")["digest_trace"]
    assert trace[0]["digest"] != trace[1]["digest"], trace
    assert trace[1]["memo_hit"] is False, trace


def test_the_rename_covered_every_production_reference():
    """The gate's rename set is the one the real operator uses -- checked against
    what formcheck recorded, not against the config that produced it."""
    detail = [r for r in _record("repaired")["rows"]
              if r["anchor"] == SYMBOL][0]["detail"]
    assert detail["references_rewritten"] == 9, detail
    assert len(detail["files_changed"]) == 5, detail
    assert "django/db/models/deletion.py" in detail["files_changed"], detail


def collect():
    """Collected at CALL time -- see `scale/test_digest.py` (CHANGES.md 19)."""
    return [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main():
    failed = 0
    tests = collect()
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {fn.__name__}\n        {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
