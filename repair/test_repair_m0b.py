"""repair-M0b: the repair removed the coupling and did not hollow out the test.

Both conditions pinned offline against committed artifacts, so they run in the
fast gate. Neither is sufficient alone, and the file asserts both or fails:

  C1  the RENAMED gold scores 1.0            the coupling is gone
  C2  behavioural mutants still score 0.0    the test still discriminates

A test that asserts nothing satisfies C1 and fails C2. The original coupled test
satisfies C2 and fails C1. Only the pair says anything.

Regenerate the artifacts with:

    ~/.venv-fc/bin/python repair/m0b_gate.py
    ~/.venv-fc/bin/python scale/run.py --instance-id pydata__xarray-4966 \
        --tests-overlay repair/overlay_repair_xarray_4966.diff \
        --records-dir repair/records_m0a/repaired

    ~/.venv-fc/bin/python repair/test_repair_m0b.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "m0b_gate_result.json")
RECORD = os.path.join(HERE, "records_m0a", "repaired", "pydata__xarray-4966.json")
BEFORE = os.path.join(HERE, "records_m0a", "plain", "pydata__xarray-4966.json")
DIFF = os.path.join(HERE, "overlay_repair_xarray_4966.diff")

MUTANTS = ("bug_noop", "bug_width", "bug_condflip")
SYMBOL = "UnsignedIntegerCoder"


def _load(path, what):
    assert os.path.exists(path), (
        f"missing {what}: {path} -- regenerate it with the command in this "
        "file's header. A missing artifact must FAIL, not skip.")
    with open(path, encoding="utf-8") as f:
        return json.load(f) if path.endswith(".json") else f.read()


def test_condition_1_renamed_gold_scores_one():
    """C1: the behaviour-preserving rename is no longer rejected."""
    gate = _load(GATE, "gate result")
    assert gate["repaired/gold_renamed"]["reward"] == 1.0, \
        gate["repaired/gold_renamed"]
    assert gate["original/gold_renamed"]["reward"] == 0.0, (
        "the original test no longer reproduces the witness -- the baseline "
        "this repair is measured against has moved")


def test_condition_2_behavioural_mutants_still_score_zero():
    """C2: the repaired test still rejects wrong programs."""
    gate = _load(GATE, "gate result")
    for name in MUTANTS:
        assert gate[f"repaired/{name}"]["reward"] == 0.0, (
            f"{name} SURVIVES the repaired test -- it was hollowed out")


def test_the_mutants_are_behavioural_not_coupled():
    """A mutant that broke the import would fail for the coupled reason and
    prove nothing. None of these name the symbol in their failure."""
    gate = _load(GATE, "gate result")
    for variant in ("original", "repaired"):
        for name in MUTANTS:
            assert gate[f"{variant}/{name}"]["names_symbol_in_log"] is False, \
                f"{variant}/{name} fails by naming {SYMBOL} -- coupled, not behavioural"


def test_detection_power_is_unchanged():
    """The strong form of "not hollowed out": the repaired test catches exactly
    what the original caught, mutant by mutant, with the same F2P breakdown."""
    gate = _load(GATE, "gate result")
    for name in MUTANTS:
        o, r = gate[f"original/{name}"], gate[f"repaired/{name}"]
        assert (o["f2p_pass"], o["f2p_fail"]) == (r["f2p_pass"], r["f2p_fail"]), (
            f"{name}: original F2P {o['f2p_pass']}/{o['f2p_fail']} vs "
            f"repaired {r['f2p_pass']}/{r['f2p_fail']} -- detection changed")


def test_the_positive_case_is_preserved():
    """G1: the untransformed gold still scores 1.0 under the repaired test."""
    gate = _load(GATE, "gate result")
    assert gate["repaired/gold"]["reward"] == 1.0, gate["repaired/gold"]


def test_formcheck_finds_no_witness_after_the_repair():
    """The harness's own verdict, before and after."""
    before, after = _load(BEFORE, "pre-repair record"), _load(RECORD, "record")
    assert [w["anchor"] for w in before["witnesses"]] == [SYMBOL], before["witnesses"]
    assert after["witnesses"] == [], [w["anchor"] for w in after["witnesses"]]

    verdicts = {label: verdict for label, verdict, _ in after["log"]}
    assert verdicts["<control>"] == "OK", verdicts
    assert verdicts[f"symbol_rename:{SYMBOL}"] == "CLEAN", verdicts


def test_the_clean_is_not_a_stale_memo():
    """A CLEAN whose digest equals the control's is D2 firing, not a result.

    The verdict alone cannot tell those apart -- both read `reward 1.0` -- which
    is why `digest_trace` exists (CHANGES.md 16, 27).
    """
    after = _load(RECORD, "record")
    trace = after["digest_trace"]
    assert trace[0]["digest"] != trace[1]["digest"], (
        "the transformed tree hashed to the control's digest: this CLEAN was "
        "served from the memo, not graded")
    assert trace[1]["memo_hit"] is False, trace


def test_the_repaired_test_names_no_internal_symbol():
    """The coupling was removed, not relocated to another private name."""
    diff = _load(DIFF, "repair diff")
    removed = [l[1:] for l in diff.splitlines()
               if l.startswith("-") and not l.startswith("---")]
    added = [l[1:] for l in diff.splitlines()
             if l.startswith("+") and not l.startswith("+++")]
    assert removed and added
    assert all(SYMBOL not in l for l in added), added
    assert any(SYMBOL in l for l in removed), removed
    # The new entry point is xarray's exported API, not another module internal.
    assert all("xr.decode_cf(" in l for l in added if "decoded =" in l), added
    assert not any("variables." in l for l in added), added


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
