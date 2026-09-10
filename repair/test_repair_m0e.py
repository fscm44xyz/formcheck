"""repair-M0e: `django__django-11433`. HOLLOWING-OUT, and C3 is what says so.

The second django task. C1 and C2 pass; C3 fails on `bug_fieldfilter`, whose
inverted `fields` filter is exactly what the coupled test exists to pin. The
repaired test reaches the same assertion through code that never runs the filter,
so it stops rejecting the mutant -- and the task reward stays 0.0 because 17 other
graded tests reject it.

The drift is ONE test inside `125/142 -> 126/142`. The count-based C3 that
shipped with M0d could not have seen it: the coupled test is PASS_TO_PASS, so the
F2P breakdown is identical under both variants. That is why C3 compares sets of
node ids here, and `test_c3_set_comparison_is_what_catches_this` pins the reason.

Regenerate with:

    ~/.venv-fc/bin/python repair/m0e_gate.py
    ~/.venv-fc/bin/python scale/run.py --instance-id django__django-11433 \
        --records-dir repair/records_m0e/plain
    ~/.venv-fc/bin/python scale/run.py --instance-id django__django-11433 \
        --tests-overlay repair/overlay_positive_django_11433.diff \
        --records-dir repair/records_m0e/positive
    ~/.venv-fc/bin/python scale/run.py --instance-id django__django-11433 \
        --tests-overlay repair/overlay_repair_django_11433.diff \
        --records-dir repair/records_m0e/repaired

    ~/.venv-fc/bin/python repair/test_repair_m0e.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "m0e_gate_result.json")
RECORDS = os.path.join(HERE, "records_m0e")
INSTANCE = "django__django-11433.json"

SYMBOL = "construct_instance"
MUTANTS = ("bug_revert", "bug_invert", "bug_fieldfilter")
VARIANTS = ("original", "import_local", "repaired")
COUPLED = "test_empty_fields_to_construct_instance (model_forms.tests.ModelFormBaseTest)"
CONTROL_TARGET = "test_blank_with_null_foreign_key_field (model_forms.tests.ModelFormBaseTest)"


def _load(path, what):
    assert os.path.exists(path), (
        f"missing {what}: {path} -- regenerate it with the command in this "
        "file's header. A missing artifact must FAIL, not skip.")
    with open(path, encoding="utf-8") as f:
        return json.load(f) if path.endswith(".json") else f.read()


def _record(name):
    return _load(os.path.join(RECORDS, name, INSTANCE), f"{name} record")


def test_positive_control_lands_and_is_scoped():
    control = _record("positive")["control"]
    assert control["passed"] is False, control
    assert "AssertionError: overlay landed" in (control["log"] or "")
    assert control["graded"]["p2p_failing"] == [CONTROL_TARGET], control["graded"]
    assert control["graded"]["f2p_fail"] == 0, control["graded"]


def test_the_blast_radius_was_almost_entirely_the_import_line():
    """Candidate pattern 2 at n=3: 142 of 143 failures were one import line."""
    gate = _load(GATE, "gate result")
    orig, local = gate["original/gold_renamed"], gate["import_local/gold_renamed"]
    assert (orig["f2p_pass"], orig["p2p_pass"]) == (0, 0), orig
    assert (local["f2p_pass"], local["f2p_fail"]) == (1, 0), local
    assert (local["p2p_pass"], local["p2p_fail"]) == (141, 1), local
    assert local["failing_ids"] == [COUPLED], local["failing_ids"]
    assert local["reward"] == 0.0, local


def test_c1_and_c2_both_pass():
    """Recorded because the point is that passing them is not sufficient."""
    gate = _load(GATE, "gate result")
    assert gate["repaired/gold_renamed"]["reward"] == 1.0, gate["repaired/gold_renamed"]
    assert gate["repaired/gold"]["reward"] == 1.0, gate["repaired/gold"]
    for name in MUTANTS:
        assert gate[f"repaired/{name}"]["reward"] == 0.0, name


def test_c3_fails_on_the_mutant_the_coupled_test_existed_to_catch():
    """THE VERDICT. `bug_fieldfilter` inverts the `fields` filter inside
    `construct_instance`; the coupled test pins exactly that. The repaired test
    reaches the same assertion through a form with no fields, so `cleaned_data`
    is empty and the filter never runs.
    """
    gate = _load(GATE, "gate result")
    orig = set(gate["original/bug_fieldfilter"]["failing_ids"])
    rep = set(gate["repaired/bug_fieldfilter"]["failing_ids"])
    assert COUPLED in orig, "the original test did not reject bug_fieldfilter"
    assert COUPLED not in rep, (
        "the repaired test now rejects bug_fieldfilter -- the recorded finding "
        "no longer holds and M0E_RESULT.md must be revisited")
    assert orig - rep == {COUPLED}, sorted(orig - rep)
    assert rep - orig == set(), sorted(rep - orig)
    # And the reward cannot see it: 0.0 under both.
    assert gate["original/bug_fieldfilter"]["reward"] == 0.0
    assert gate["repaired/bug_fieldfilter"]["reward"] == 0.0


def test_c3_set_comparison_is_what_catches_this():
    """Why C3 had to stop comparing counts.

    The coupled test is PASS_TO_PASS, so the F2P breakdown -- what the M0d
    implementation compared -- is identical under both variants. The drift is one
    test inside a P2P count the mutant moves by seventeen.
    """
    gate = _load(GATE, "gate result")
    o, r = gate["original/bug_fieldfilter"], gate["repaired/bug_fieldfilter"]
    assert (o["f2p_pass"], o["f2p_fail"]) == (r["f2p_pass"], r["f2p_fail"]), (
        "the F2P breakdown differs, so the old count-based C3 would have caught "
        "this and the stated reason for changing it is wrong")
    assert (o["p2p_fail"], r["p2p_fail"]) == (17, 16), (o["p2p_fail"], r["p2p_fail"])


def test_the_other_mutants_show_no_drift():
    gate = _load(GATE, "gate result")
    for name in ("bug_revert", "bug_invert"):
        assert (set(gate[f"original/{name}"]["failing_ids"])
                == set(gate[f"repaired/{name}"]["failing_ids"])), name


def test_every_mutant_actually_ran_the_graded_suite():
    gate = _load(GATE, "gate result")
    baseline = gate["repaired/gold"]["graded_ids_present"]
    assert baseline == 143, baseline
    for variant in VARIANTS:
        for name in MUTANTS:
            got = gate[f"{variant}/{name}"]["graded_ids_present"]
            assert got == baseline, (variant, name, got, baseline)


def test_the_mutants_are_behavioural_not_coupled():
    gate = _load(GATE, "gate result")
    for variant in VARIANTS:
        for name in MUTANTS:
            assert gate[f"{variant}/{name}"]["names_symbol_in_log"] is False, \
                f"{variant}/{name} fails by naming {SYMBOL}"


def test_formcheck_reports_clean_on_a_repair_that_fails_c3():
    """Second confirmation of the M0d finding, same repo, different task."""
    before, after = _record("plain"), _record("repaired")
    assert [w["anchor"] for w in before["witnesses"]] == [SYMBOL], before["witnesses"]
    assert after["witnesses"] == [], after["witnesses"]
    verdicts = {label: verdict for label, verdict, _ in after["log"]}
    assert verdicts[f"symbol_rename:{SYMBOL}"] == "CLEAN", verdicts


def test_the_clean_is_not_a_stale_memo():
    trace = _record("repaired")["digest_trace"]
    assert trace[0]["digest"] != trace[1]["digest"], trace
    assert trace[1]["memo_hit"] is False, trace


def test_the_two_shipped_repairs_still_pass_the_stricter_c3():
    """M0b and M0c were accepted under the count-based C3. Re-run under the
    set-based one they still show no drift, on every mutant."""
    for gate_file, mutants in (
            ("m0b_gate_result.json", ("bug_noop", "bug_width", "bug_condflip")),
            ("m0c_gate_result.json", ("bug_revert", "bug_leftblock", "bug_stackorder"))):
        gate = _load(os.path.join(HERE, gate_file), gate_file)
        for name in mutants:
            assert (set(gate[f"original/{name}"]["failing_ids"])
                    == set(gate[f"repaired/{name}"]["failing_ids"])), \
                (gate_file, name)


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
