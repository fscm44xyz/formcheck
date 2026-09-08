"""Prove every guard CAN fire.

`CHANGES.md` 23: the burn detector never triggered once in its life, which made
it indistinguishable from a guard that *could* not trigger — and for refusals it
could not, because another guard's early `return` skipped the line that fed it.
Both mechanisms were individually correct. They cancelled at the seam, silently,
and no review of either one alone would have found it.

The general rule this file exists to enforce:

    A guard that has never fired in production is indistinguishable from a
    guard that cannot fire. Every invariant needs a test that proves it is
    CAPABLE of firing, run alongside the others.

So these tests assert the failure path, not the happy one. Each drives the real
mechanism to its raise. A test that only checks the predicate — `all(t < floor)`
— proves arithmetic, not that anything happens; that weaker form is what this
file replaces.

    ~/.venv-fc/bin/python scale/test_guards_fire.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "repro"))

import diff_verdicts  # noqa: E402
import rotation  # noqa: E402
import run  # noqa: E402


def _must_raise(exc_type, fn, what):
    try:
        fn()
    except exc_type:
        return
    raise AssertionError(f"{what}: guard did NOT fire")


# --- the burn detector, which had never fired ------------------------------

def test_burn_detector_fires_on_fast_completions():
    _must_raise(run.BurnDetected,
                lambda: run.check_progress([2.5] * run.BURN_STREAK),
                "burn detector on fast completions")


def test_burn_detector_fires_on_a_refusal_storm():
    """The case that actually happened: 107 refusals, detector never looked."""
    _must_raise(run.BurnDetected,
                lambda: run.check_progress([0.0] * run.BURN_STREAK),
                "burn detector on refusals")


def test_burn_detector_emits_an_abort_event_when_it_fires():
    """Firing silently would leave the same hole one level up."""
    events = []
    try:
        run.check_progress([0.0] * run.BURN_STREAK,
                           lambda **kw: events.append(kw))
    except run.BurnDetected:
        pass
    assert events and events[0]["event"] == "abort", events
    assert events[0]["reason"] == "burn pattern", events


def test_burn_detector_does_not_fire_on_a_healthy_run():
    run.check_progress([180.0] * run.BURN_STREAK)
    run.check_progress([0.0] * (run.BURN_STREAK - 1) + [180.0])
    run.check_progress([0.0] * (run.BURN_STREAK - 1))  # not enough yet


# --- the disk-cleanup guard, which had never fired on real data ------------

def test_cleanup_guard_fires_on_a_leaked_image():
    _must_raise(
        rotation.DiskBudgetError,
        lambda: run.check_task_cleanup("img", True, [], None, "task-x"),
        "cleanup guard on a leaked image")


def test_cleanup_guard_fires_on_a_leaked_container():
    _must_raise(
        rotation.DiskBudgetError,
        lambda: run.check_task_cleanup("img", False, ["validate-x"], None, "t"),
        "cleanup guard on a leaked container")


def test_cleanup_guard_is_silent_when_the_task_cleaned_up():
    run.check_task_cleanup("img", False, [], None, "t")


# --- the frozen-baseline pin, which had never fired ------------------------

def test_baseline_pin_fires_when_the_reference_changes(tmp=None):
    """`repro/f2_gate.py` rewrites the M0 reference as a side effect of running.
    The pin exists to catch that; it had never been shown to."""
    import hashlib
    import json
    import tempfile

    d = tempfile.mkdtemp()
    ref = os.path.join(d, "f2_verdicts.json")
    with open(ref, "w", encoding="utf-8") as f:
        json.dump([{"operator": "x", "anchor": None, "verdict": "CLEAN"}], f)
    fixtures = os.path.join(HERE, "fixtures")
    pin = os.path.join(fixtures, "f2_verdicts.sha256")
    saved = open(pin, encoding="utf-8").read() if os.path.exists(pin) else None
    try:
        with open(pin, "w", encoding="utf-8") as f:
            f.write(hashlib.sha256(b"something else entirely").hexdigest())
        _must_raise(RuntimeError,
                    lambda: diff_verdicts.assert_reference_unmodified(ref),
                    "baseline pin on a modified reference")
    finally:
        if saved is not None:
            with open(pin, "w", encoding="utf-8") as f:
                f.write(saved)


def test_baseline_pin_passes_on_the_real_reference():
    real = os.path.join(os.path.dirname(HERE), "repro", "f2_verdicts.json")
    if os.path.exists(real):
        diff_verdicts.assert_reference_unmodified(real)


# --- headroom and merged-rate guards (already had proofs; kept together) ---

def test_headroom_guard_fires():
    original = rotation.free_bytes
    rotation.free_bytes = lambda path=None: 1024
    try:
        _must_raise(rotation.NotEnoughDisk,
                    lambda: rotation.ensure_headroom(4 * 1024 ** 3),
                    "headroom guard")
    finally:
        rotation.free_bytes = original


def test_merged_rate_guard_fires():
    import aggregate
    _must_raise(aggregate.MergedRateError,
                lambda: aggregate._forbid_merged({"x": {"rate": 0.5}}),
                "merged-rate guard")


def test_digest_guard_fires():
    from test_digest import FakeCompleted, make_task
    _must_raise(RuntimeError,
                lambda: make_task(lambda s: FakeCompleted("", "boom", 1))
                ._tree_digest(),
                "digest guard on empty output")


def collect():
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
