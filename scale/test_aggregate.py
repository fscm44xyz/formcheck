"""Pin the aggregate's guards as tests rather than interactive checks.

The no-merged-percentage rule (`writeup.md` 6.5, `CHANGES.md` 2) is enforced
structurally: `witness_rate` has no operator-less arity, and `_forbid_merged`
refuses to serialize a report containing a rate that does not name its operator.
Both were verified by hand when written. Verified by hand is verified once.

Also pins the denominator rule of `writeup.md` 4.1 -- a task whose control failed
is excluded, never counted as "no witness found" -- and that Wilson does not
collapse at a zero numerator, which is where a null result lives.

    ~/.venv-fc/bin/python scale/test_aggregate.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import aggregate as A  # noqa: E402


def record(instance_id, control_passed, rows, multi=False):
    return {
        "instance_id": instance_id,
        "control": {"passed": control_passed, "reason": "x"},
        "rows": rows, "witnesses": [r for r in rows if r["verdict"] == "WITNESS"],
        "multi_target": multi, "on_prime_hub": None, "error": None,
    }


def row(operator, verdict, loud=True, anchor="a", observable="symbol identity"):
    return {"operator": operator, "verdict": verdict, "anchor": anchor,
            "file": "f.py", "loud_failure": loud, "observable": observable,
            "reason": "", "tier": "MEDIUM"}


# --- the structural no-merged-rate rule ------------------------------------

def test_witness_rate_has_no_operator_less_arity():
    for bad in (None, "", 0, [], {}):
        try:
            A.witness_rate([], bad)
        except A.MergedRateError:
            continue
        raise AssertionError(f"accepted {bad!r} as an operator")


def test_forbid_merged_rejects_an_unattributed_rate():
    try:
        A._forbid_merged({"overall": {"rate": 0.42}})
    except A.MergedRateError as exc:
        assert "never aggregated" in str(exc), exc
    else:
        raise AssertionError("an unattributed rate must not serialize")


def test_forbid_merged_finds_a_rate_nested_in_a_list():
    """The guard walks the whole structure, not just the top level."""
    try:
        A._forbid_merged({"xs": [{"ok": 1}, {"rate": 0.5}]})
    except A.MergedRateError as exc:
        assert "xs[1]" in str(exc), exc
    else:
        raise AssertionError("nested unattributed rates must be caught")


def test_forbid_merged_allows_an_attributed_rate():
    A._forbid_merged({"x": {"operator": "symbol_rename", "rate": 0.42}})


def test_a_null_rate_is_not_flagged():
    """`rate: None` means nothing was judged, which is not a merged number."""
    A._forbid_merged({"x": {"rate": None}})


# --- the denominator rule (writeup.md 4.1) ---------------------------------

def test_a_failed_control_is_excluded_from_the_denominator():
    """Counting it as "no witness found" would convert a broken harness into
    evidence of a clean reward."""
    records = [
        record("ok", True, [row("symbol_rename", "CLEAN")]),
        record("broken", False, [row("symbol_rename", "CLEAN")]),
    ]
    assert len(A.controlled(records)) == 1
    r = A.witness_rate(records, "symbol_rename")
    assert r["judged_tasks"] == 1, r


def test_a_task_with_nothing_judged_is_not_in_the_denominator():
    """REFUSED and NOT_APPLICABLE are not judgements."""
    records = [
        record("a", True, [row("symbol_rename", "REFUSED")]),
        record("b", True, [row("symbol_rename", "NOT_APPLICABLE")]),
        record("c", True, [row("symbol_rename", "WITNESS")]),
    ]
    r = A.witness_rate(records, "symbol_rename")
    assert (r["witness_tasks"], r["judged_tasks"]) == (1, 1), r


def test_a_task_counts_once_however_many_witness_rows_it_has():
    records = [record("a", True, [row("symbol_rename", "WITNESS", anchor="x"),
                                  row("symbol_rename", "WITNESS", anchor="y")])]
    r = A.witness_rate(records, "symbol_rename")
    assert (r["witness_tasks"], r["judged_tasks"]) == (1, 1), r


def test_operators_are_counted_separately_and_never_pooled():
    records = [record("a", True, [row("symbol_rename", "WITNESS"),
                                  row("collection_reverse", "UNVALIDATED",
                                      loud=False)])]
    counts = A.verdict_counts(records)
    assert counts["symbol_rename"] == {"WITNESS": 1}
    assert counts["collection_reverse"] == {"UNVALIDATED": 1}


def test_loud_silent_partition_follows_the_row_not_the_operator_table():
    records = [record("a", True, [row("symbol_rename", "WITNESS", loud=True),
                                  row("collection_reverse", "UNVALIDATED",
                                      loud=False)])]
    p = A.loud_silent_partition(records)
    assert p["loud"]["witnesses"] == 1 and p["silent"]["witnesses"] == 0
    assert p["silent"]["judged"] == 0, p["silent"]


# --- Wilson ----------------------------------------------------------------

def test_wilson_does_not_collapse_at_zero():
    """The normal approximation gives [0,0] at 0/12, which would read as "no
    coupling exists" from twelve observations."""
    lo, hi = A.wilson(0, 12)
    assert lo == 0.0 and hi > 0.2, (lo, hi)


def test_wilson_is_none_without_trials():
    assert A.wilson(0, 0) is None


def test_wilson_brackets_the_point_estimate():
    lo, hi = A.wilson(3, 50)
    assert lo < 3 / 50 < hi, (lo, hi)


def collect():
    """Collected at CALL time, not import time.

    A module-level `TESTS = [...]` binds before anything defined below it, so a
    test appended to the end of the file is silently never run -- which happened
    here, to the four tests pinning CHANGES.md 18, and a suite that quietly skips
    tests is the same silent-omission class this project keeps finding.
    """
    return [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main():
    tests = collect()
    failed = 0
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
