"""repair-M0c: `astropy__astropy-12907`, the import shape.

Same two conditions as M0b, plus the measurement that makes this case different:
how much of the 15-test blast radius was the module-level import line, and how
much was the one test whose subject is the renamed symbol.

Regenerate the artifacts with:

    ~/.venv-fc/bin/python repair/m0c_gate.py
    ~/.venv-fc/bin/python scale/run.py --instance-id astropy__astropy-12907 \
        --records-dir repair/records_m0c/plain
    ~/.venv-fc/bin/python scale/run.py --instance-id astropy__astropy-12907 \
        --tests-overlay repair/overlay_repair_astropy_12907.diff \
        --records-dir repair/records_m0c/repaired
    ~/.venv-fc/bin/python scale/run.py --instance-id astropy__astropy-12907 \
        --tests-overlay repair/overlay_positive_astropy_12907.diff \
        --records-dir repair/records_m0c/positive

    ~/.venv-fc/bin/python repair/test_repair_m0c.py
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "m0c_gate_result.json")
RECORDS = os.path.join(HERE, "records_m0c")
INSTANCE = "astropy__astropy-12907.json"
DIFF = os.path.join(HERE, "overlay_repair_astropy_12907.diff")

SYMBOL = "_cstack"
MUTANTS = ("bug_revert", "bug_leftblock", "bug_stackorder")
VARIANTS = ("original", "import_local", "repaired")
TARGETED = {"astropy/modeling/tests/test_separable.py::test_cstack"}


def _load(path, what):
    assert os.path.exists(path), (
        f"missing {what}: {path} -- regenerate it with the command in this "
        "file's header. A missing artifact must FAIL, not skip.")
    with open(path, encoding="utf-8") as f:
        return json.load(f) if path.endswith(".json") else f.read()


def _record(name):
    return _load(os.path.join(RECORDS, name, INSTANCE), f"{name} record")


# --- the overlay surface, on a second repo ---------------------------------

def test_positive_control_lands_and_is_scoped():
    """The M0a standard, re-established on astropy rather than assumed from
    xarray: an overlay that names itself in the graded log, breaking exactly the
    node ids it targets and nothing else."""
    control = _record("positive")["control"]
    assert control["passed"] is False, control
    log = control["log"] or ""
    assert log.count("AssertionError: overlay landed") == 1, log.count(
        "AssertionError: overlay landed")

    states = {}
    for line in log.splitlines():
        m = re.match(r"^(PASSED|FAILED|ERROR)\s+(\S+)", line.strip())
        if m:
            states[m.group(2)] = m.group(1)
    assert len(states) == 15, len(states)
    failed = {t for t, s in states.items() if s != "PASSED"}
    assert failed == TARGETED, sorted(failed)


# --- the two conditions -----------------------------------------------------

def test_condition_1_renamed_gold_scores_one():
    gate = _load(GATE, "gate result")
    assert gate["repaired/gold_renamed"]["reward"] == 1.0, \
        gate["repaired/gold_renamed"]
    assert gate["original/gold_renamed"]["reward"] == 0.0, (
        "the original test no longer reproduces the witness -- the baseline "
        "this repair is measured against has moved")


def test_condition_2_behavioural_mutants_still_score_zero():
    gate = _load(GATE, "gate result")
    for name in MUTANTS:
        assert gate[f"repaired/{name}"]["reward"] == 0.0, (
            f"{name} SURVIVES the repaired test -- it was hollowed out")


def test_the_mutants_are_behavioural_not_coupled():
    gate = _load(GATE, "gate result")
    for variant in VARIANTS:
        for name in MUTANTS:
            assert gate[f"{variant}/{name}"]["names_symbol_in_log"] is False, \
                f"{variant}/{name} fails by naming {SYMBOL} -- coupled, not behavioural"


def test_detection_power_is_unchanged():
    """Mutant by mutant, across all three variants, the same breakdown."""
    gate = _load(GATE, "gate result")
    for name in MUTANTS:
        seen = {(gate[f"{v}/{name}"]["f2p_pass"], gate[f"{v}/{name}"]["f2p_fail"],
                 gate[f"{v}/{name}"]["p2p_pass"], gate[f"{v}/{name}"]["p2p_fail"])
                for v in VARIANTS}
        assert len(seen) == 1, f"{name}: detection differs across variants: {seen}"


def test_the_positive_case_is_preserved():
    gate = _load(GATE, "gate result")
    assert gate["repaired/gold"]["reward"] == 1.0, gate["repaired/gold"]


# --- what makes this case different from xarray -----------------------------

def test_the_blast_radius_was_almost_entirely_the_import_line():
    """THE MEASUREMENT. One module-level `from ... import` naming `_cstack`
    takes down all 15 graded tests; 14 of them never use the symbol.

    `import_local` changes nothing but where `_cstack` is imported. Under the
    rename it recovers 14 of the 15 and still scores 0.0, because the last one
    is the test whose SUBJECT is the renamed symbol. That is the split between
    collateral and intrinsic coupling, and it is why this case needed a
    different repair from xarray's rather than the same one.
    """
    gate = _load(GATE, "gate result")
    orig = gate["original/gold_renamed"]
    local = gate["import_local/gold_renamed"]

    # Original: the module does not import, so nothing passes.
    assert (orig["f2p_pass"], orig["p2p_pass"]) == (0, 0), orig
    # Import-local: everything passes except the one intrinsically coupled test.
    assert (local["f2p_pass"], local["f2p_fail"]) == (2, 0), local
    assert (local["p2p_pass"], local["p2p_fail"]) == (12, 1), local
    assert local["p2p_failing"] == sorted(TARGETED), local["p2p_failing"]
    # And it is still not a repair: C1 needs 1.0, not 14/15.
    assert local["reward"] == 0.0, local


# --- formcheck's own verdict ------------------------------------------------

def test_formcheck_finds_no_witness_after_the_repair():
    before, after = _record("plain"), _record("repaired")
    assert [w["anchor"] for w in before["witnesses"]] == [SYMBOL], before["witnesses"]
    assert after["witnesses"] == [], [w["anchor"] for w in after["witnesses"]]
    verdicts = {label: verdict for label, verdict, _ in after["log"]}
    assert verdicts["<control>"] == "OK", verdicts
    assert verdicts[f"symbol_rename:{SYMBOL}"] == "CLEAN", verdicts


def test_the_clean_is_not_a_stale_memo():
    trace = _record("repaired")["digest_trace"]
    assert trace[0]["digest"] != trace[1]["digest"], (
        "the transformed tree hashed to the control's digest: this CLEAN was "
        "served from the memo, not graded")
    assert trace[1]["memo_hit"] is False, trace


def test_the_repaired_test_names_no_internal_symbol():
    """The coupling was removed, not relocated to another private name."""
    diff = _load(DIFF, "repair diff")
    added = [l[1:] for l in diff.splitlines()
             if l.startswith("+") and not l.startswith("+++")]
    assert added
    assert all(SYMBOL not in l for l in added), added
    # Every added call goes through the module's exported API.
    calls = [l for l in added if "result = " in l]
    assert calls and all("separability_matrix(" in l for l in calls), calls
    assert not any(re.search(r"\b_[a-z]", l) for l in calls), calls


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
