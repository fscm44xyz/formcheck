"""Pin `xarray-4966` to WITNESS. This bug has been shipped twice.

`writeup.md` 6.2's rule: a failing test whose message names the renamed symbol
is asserting that NAME, and an alpha-rename changes no expression's value -- so
that failure is COUPLING, not broken behaviour. A test failing any other way
means the rewrite really did change behaviour, and the transform is INVALID.

Phase 4 wrote that rule after shipping the collapsed version. M1's `SuiteOracle`
then reintroduced the collapsed version in a different file, on a code path
Phase 4's fix never touched (`CHANGES.md` 13), and it turned `xarray-4966` --
the entire evidence for 6.2 -- from WITNESS into INVALID. Twice in two files is
enough: this test exists so a third time fails loudly and offline.

It runs against a RECORDED log from a real container run
(`scale/fixtures/xarray_4966_rename.json`, captured by
`scale/run.py --instance-id pydata__xarray-4966`), so it needs no docker, no
network, and about a millisecond. A test that requires a 5 GiB pull is a test
nobody runs.

    ~/.venv-fc/bin/python scale/test_partition.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "repro"))

from container_task import classify_failures  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "xarray_4966_rename.json")

# The four PASS_TO_PASS tests `writeup.md` 6.2 is about: pre-existing tests that
# fail purely because they reach the renamed class as a module attribute.
EXPECTED_P2P = [
    "xarray/tests/test_coding.py::test_decode_unsigned_from_signed[1]",
    "xarray/tests/test_coding.py::test_decode_unsigned_from_signed[2]",
    "xarray/tests/test_coding.py::test_decode_unsigned_from_signed[4]",
    "xarray/tests/test_coding.py::test_decode_unsigned_from_signed[8]",
]
EXPECTED_F2P = [
    "xarray/tests/test_coding.py::test_decode_signed_from_unsigned[1]",
    "xarray/tests/test_coding.py::test_decode_signed_from_unsigned[2]",
    "xarray/tests/test_coding.py::test_decode_signed_from_unsigned[4]",
    "xarray/tests/test_coding.py::test_decode_signed_from_unsigned[8]",
]


def load():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def test_every_failure_is_coupling():
    """All eight failing tests fail because the symbol's NAME changed."""
    fx = load()
    a = classify_failures(fx["log"], fx["graded"], fx["symbol"])
    assert sorted(a["coupled"]) == sorted(EXPECTED_P2P + EXPECTED_F2P), a["coupled"]
    assert a["unexplained"] == [], a["unexplained"]
    assert a["all_reference_the_symbol"] is True


def test_verdict_is_witness_not_invalid():
    """The oracle must call this transform behaviour-preserving.

    `SuiteOracle.check` returns `not unexplained`; True means the transform
    preserved behaviour, so the hook goes on to grade it, finds reward 0.0, and
    records WITNESS. False would mean INVALID -- the bug.
    """
    fx = load()
    a = classify_failures(fx["log"], fx["graded"], fx["symbol"])
    satisfied = not a["unexplained"]
    assert satisfied is True, (
        "xarray-4966 classified as INVALID: the writeup.md 6.2 partition has "
        "been lost again. See CHANGES.md 13.")
    assert fx["graded"]["reward"] == 0.0, "a WITNESS requires reward 0.0"


def test_the_collapsed_rule_would_get_it_wrong():
    """Pin the bug itself, so the test cannot pass vacuously.

    If someone reverts to `p2p_fail == 0`, that rule says the transform broke
    behaviour. This asserts the two rules genuinely disagree on this fixture --
    otherwise the tests above would still pass on a broken implementation.
    """
    fx = load()
    collapsed_says_preserved = fx["graded"]["p2p_fail"] == 0
    assert collapsed_says_preserved is False
    a = classify_failures(fx["log"], fx["graded"], fx["symbol"])
    assert (not a["unexplained"]) != collapsed_says_preserved


def test_an_unrelated_failure_is_still_invalid():
    """The partition must not wave everything through.

    A failure that does not name the symbol is real breakage and must stay
    unexplained, or the rule would classify every broken transform as coupling.
    """
    log = ("____ test_unrelated ____\n"
           "E       ValueError: arithmetic changed\n")
    graded = {"p2p_failing": ["x/tests/test_coding.py::test_unrelated"],
              "f2p_failing": []}
    a = classify_failures(log, graded, "UnsignedIntegerCoder")
    assert a["coupled"] == []
    assert len(a["unexplained"]) == 1
    assert a["all_reference_the_symbol"] is False


def test_a_missing_failure_section_is_not_assumed_to_be_coupling():
    """No failure block found means we cannot say why it failed -- so we do not
    say it was coupling. Fail toward INVALID, never toward WITNESS."""
    graded = {"p2p_failing": ["x/tests/test_coding.py::test_ghost"],
              "f2p_failing": []}
    a = classify_failures("no failure blocks here", graded, "Sym")
    assert a["coupled"] == []
    assert "no failure section found" in a["unexplained"][0]


def test_suite_oracle_itself_returns_preserved():
    """Exercise `SuiteOracle.check`, not just the helper it calls.

    The tests above would all still pass if someone left `classify_failures`
    alone and changed the oracle back to `p2p_fail == 0`, which is exactly how
    the bug arrived the second time -- a new file reimplementing the decision.
    So the decision itself is pinned here, through a fake task that replays the
    recorded grading.
    """
    import asyncio

    from container_task import SuiteOracle

    fx = load()

    class FakeTask:
        graded_log = fx["log"]

        async def graded_report(self, runtime):
            return fx["graded"]

    report = {"loud_failure": True, "name": fx["symbol"],
              "observable": "symbol identity (module-level name)"}
    satisfied = asyncio.run(SuiteOracle().check(FakeTask(), None, report))
    assert satisfied is True, (
        "SuiteOracle.check called xarray-4966 a broken transform. The "
        "writeup.md 6.2 partition has been lost again -- CHANGES.md 13.")


def test_suite_oracle_refuses_to_judge_a_silent_operator():
    """`loud_failure` False must stay UNVALIDATED, not become a verdict.

    This is the other half of what keeps THE NUMBER symbol_rename-only; a change
    that made the oracle judge silent operators would inflate every rate.
    """
    import asyncio

    from container_task import SuiteOracle

    report = {"loud_failure": False, "name": "X", "observable": "order"}
    assert asyncio.run(SuiteOracle().check(object(), None, report)) is None


def collect():
    """Collected at CALL time, not import time.

    A module-level `TESTS = [...]` binds before anything defined below it, so a
    test appended to the end of the file is silently never run -- which happened
    here, to the four tests pinning CHANGES.md 18, and a suite that quietly skips
    tests is the same silent-omission class this project keeps finding.
    """
    return [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main():
    if not os.path.exists(FIXTURE):
        print(f"FIXTURE MISSING: {FIXTURE}\n"
              "Regenerate with:\n"
              "  ~/.venv-fc/bin/python scale/run.py "
              "--instance-id pydata__xarray-4966")
        return 2
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




# ---------------------------------------------------------------------------
# CHANGES.md 18: SWE-bench is not one test runner, and the attribution has to
# understand every shape it emits or it reports coupling as breakage.
# ---------------------------------------------------------------------------

M3_FIXTURE = os.path.join(HERE, "fixtures", "m3_misattributed_logs.json")


def _m3_cases():
    with open(M3_FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def test_pytest_collection_error_is_attributed():
    """`______ ERROR collecting path ______` -- one block for a whole module
    that would not import. An alpha-rename a test imports by name produces
    exactly this and no per-test blocks at all."""
    case = _m3_cases()["astropy__astropy-12907"]
    a = classify_failures(case["log"], case["graded"], case["symbol"])
    assert a["unexplained"] == [], a["unexplained"][:2]
    assert len(a["coupled"]) == 12, len(a["coupled"])


def test_django_unittest_error_blocks_are_attributed():
    """django runs `runtests.py`, whose output has no underscore rules at all:
    `====` then `ERROR: name (mod.Class)` then `----` then the traceback."""
    case = _m3_cases()["django__django-15572"]
    a = classify_failures(case["log"], case["graded"], case["symbol"])
    assert a["unexplained"] == [], a["unexplained"][:2]
    assert len(a["coupled"]) == 4, len(a["coupled"])


def test_django_module_import_failure_is_attributed():
    """The hardest shape: django reports a module that would not import as a
    synthetic `test_cookie (unittest.loader._FailedTest)`, naming the MODULE and
    never the tests that were wanted."""
    case = _m3_cases()["django__django-13195"]
    a = classify_failures(case["log"], case["graded"], case["symbol"])
    assert a["unexplained"] == [], a["unexplained"][:2]
    assert len(a["coupled"]) == 11, len(a["coupled"])


def test_pylint_collection_error_is_attributed():
    case = _m3_cases()["pylint-dev__pylint-4604"]
    a = classify_failures(case["log"], case["graded"], case["symbol"])
    assert a["unexplained"] == [], a["unexplained"][:2]
    assert len(a["coupled"]) == 21, len(a["coupled"])


def test_every_m3_misattribution_is_now_coupling():
    """All four together: these were reported INVALID, and every one is a
    WITNESS. Reported W over M3 went from 0 to 4 on this fix alone."""
    for iid, case in _m3_cases().items():
        a = classify_failures(case["log"], case["graded"], case["symbol"])
        assert a["all_reference_the_symbol"] is True, (iid, a["unexplained"][:2])


def test_a_per_test_block_still_beats_a_collection_error():
    """Order matters: a test with its own failure block failed on its own terms.
    Only a test with no block of its own may be explained by the module."""
    log = ("______ ERROR collecting t/test_x.py ______\n"
           "E   ImportError: cannot import name 'Sym'\n"
           "______ test_real ______\n"
           "E   ValueError: genuinely broken\n")
    graded = {"p2p_failing": ["t/test_x.py::test_real"], "f2p_failing": []}
    a = classify_failures(log, graded, "Sym")
    assert a["coupled"] == [], a["coupled"]
    assert len(a["unexplained"]) == 1, a["unexplained"]


def test_the_three_known_shapes_are_handled_explicitly():
    """pytest per-test, pytest collection error, unittest/django _FailedTest."""
    from f4_formcheck import failure_sections, section_for
    per_test = "______ test_a ______\nE   AttributeError: no attribute 'S'\n"
    collect = ("______ ERROR collecting t/test_a.py ______\n"
               "E   ImportError: cannot import name 'S'\n")
    django = ("======================================================\n"
              "ERROR: test_a (mod.pkg.Cls)\n"
              "------------------------------------------------------\n"
              "AttributeError: module 'm' has no attribute 'S'\n")
    assert section_for(failure_sections(per_test), "t/test_a.py::test_a")
    assert section_for(failure_sections(collect), "t/test_a.py::test_a")
    assert section_for(failure_sections(django), "test_a (mod.pkg.Cls)")


def test_an_unknown_fourth_shape_is_unparsed_not_broken():
    """THE CONTRACT THAT CLOSES CHANGES.md 18.

    A runner nobody has met must make the case UNJUDGEABLE and say so. It must
    never be reported as breakage, because that is the exact mechanism that
    suppressed four witnesses and inverted M3's headline while every operational
    signal stayed green.
    """
    log = "SomeOtherRunner v3\n!!! test_a did not pass !!!\n"
    graded = {"p2p_failing": ["t/test_a.py::test_a"], "f2p_failing": []}
    a = classify_failures(log, graded, "S")
    assert a["unparsed"] == ["t/test_a.py::test_a"], a
    assert a["broke"] == [], a
    assert a["unparsed_log_shape"] is True


def test_the_oracle_declines_to_judge_an_unparsed_log():
    """`None`, which the hook renders UNVALIDATED -- not False, which is
    INVALID."""
    import asyncio

    from container_task import SuiteOracle

    class FakeTask:
        graded_log = "SomeOtherRunner\n!!! nope !!!\n"

        async def graded_report(self, runtime):
            return {"p2p_failing": ["t/x.py::test_a"], "f2p_failing": []}

    report = {"loud_failure": True, "name": "S", "observable": "symbol identity"}
    assert asyncio.run(SuiteOracle().check(FakeTask(), None, report)) is None


def test_genuine_breakage_is_still_invalid():
    """The partition must not turn every failure into "we could not tell"."""
    log = "______ test_a ______\nE   ValueError: arithmetic changed\n"
    graded = {"p2p_failing": ["t/test_a.py::test_a"], "f2p_failing": []}
    a = classify_failures(log, graded, "S")
    assert a["broke"] == ["t/test_a.py::test_a"], a
    assert a["unparsed"] == [], a


SYMPY_LOG = """
________________ sympy/polys/tests/test_rings.py:test_bug_sqrt ________________
Traceback (most recent call last):
  File "/testbed/sympy/polys/tests/test_rings.py", line 12, in test_bug_sqrt
    from sympy.polys.rings import FracField
ImportError: cannot import name 'FracField'
"""


def test_sympy_bin_test_shape_is_attributed():
    """The FOURTH shape, found by the closure rather than by a wrong number.

    sympy's blocks ARE underscore-delimited so they parse, but the label is
    `path/to/test_x.py:test_name` while swebench's sympy parser reports failing
    tests by their BARE name. `header.split(".")[-1]` yields `py:test_name`, so
    the header was sitting right there and was missed on punctuation.
    """
    a = classify_failures(SYMPY_LOG,
                          {"p2p_failing": ["test_bug_sqrt"], "f2p_failing": []},
                          "FracField")
    assert a["coupled"] == ["test_bug_sqrt"], a
    assert a["unparsed"] == [] and a["broke"] == [], a


def test_sympy_path_form_test_id_also_matches():
    a = classify_failures(
        SYMPY_LOG,
        {"p2p_failing": ["sympy/polys/tests/test_rings.py:test_bug_sqrt"],
         "f2p_failing": []}, "FracField")
    assert a["unparsed"] == [], a


def test_the_sympy_rule_does_not_swallow_unrelated_failures():
    """Matching after the last colon must not make everything match."""
    a = classify_failures(SYMPY_LOG,
                          {"p2p_failing": ["test_something_else"],
                           "f2p_failing": []}, "FracField")
    assert a["unparsed"] == ["test_something_else"], a


if __name__ == "__main__":
    sys.exit(main())
