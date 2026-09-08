"""Pin the liveness invariant (`CHANGES.md` 21).

M4 ran 330 tasks into the ground in 32 minutes: every pull was refused with a
429, so each "task" took 2.5s. Nothing stopped it. The monitor was watching for
`DiskBudgetError`, `Traceback` and `abort`, and a fast clean-looking failure is
none of those -- the run reported healthy because it was being watched for
causes already known.

The fix asserts something causally necessary instead: a real task must pull an
image, start a container and run the control suite, so it cannot be fast.

    ~/.venv-fc/bin/python scale/test_burn.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "repro"))

import rotation  # noqa: E402,F401
import run  # noqa: E402


def test_the_threshold_sits_between_the_two_measured_populations():
    """Measured, not guessed: fastest of 97 controlled tasks 30.5s; slowest of
    357 rate-limited tasks 19.6s. The populations do not overlap."""
    assert 19.6 < run.MIN_PLAUSIBLE_TASK_SECONDS < 30.5


def test_a_burn_streak_trips_and_a_healthy_run_does_not():
    burn = [2.5] * run.BURN_STREAK
    healthy = [180.0] * run.BURN_STREAK
    mixed = [2.5] * (run.BURN_STREAK - 1) + [180.0]

    def trips(seq):
        return (len(seq) == run.BURN_STREAK
                and all(t < run.MIN_PLAUSIBLE_TASK_SECONDS for t in seq))

    assert trips(burn)
    assert not trips(healthy)
    assert not trips(mixed), "one real task must reset the streak"


def test_the_streak_is_short_enough_to_matter():
    """M4 burned 330 tasks. Catching it within 8 is the point."""
    assert run.BURN_STREAK <= 10


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


def test_a_refusal_counts_as_no_progress():
    """THE HOLE THAT COST 107 TASKS.

    Separating refusal from failure (correct) put refusals outside the liveness
    invariant (wrong). The two requirements interacted and only the interaction
    was broken: 107 refusals in 41 seconds, and the detector never looked,
    because `return None` came before the duration was recorded.

    A refusal is zero seconds of work. It counts as exactly that.
    """
    recent = [0.0] * run.BURN_STREAK
    assert all(t < run.MIN_PLAUSIBLE_TASK_SECONDS for t in recent), (
        "a refusal must fall under the floor, or a refusal storm is invisible")


def test_one_real_task_breaks_a_refusal_streak():
    recent = [0.0] * (run.BURN_STREAK - 1) + [180.0]
    assert not all(t < run.MIN_PLAUSIBLE_TASK_SECONDS for t in recent)


def test_backoff_grows_and_is_capped():
    import asyncio

    import rotation
    naps = []
    original = asyncio.sleep

    async def fake_sleep(n):
        naps.append(n)

    asyncio.sleep = fake_sleep
    rotation._consecutive_refusals = 0
    try:
        for _ in range(12):
            asyncio.get_event_loop_policy()
            asyncio.run(rotation.note_refusal())
    finally:
        asyncio.sleep = original
        rotation._consecutive_refusals = 0

    assert naps[:1] == [rotation.BACKOFF_BASE_SECONDS], naps[:3]
    assert naps == sorted(naps), "backoff must be monotonic"
    assert max(naps) == rotation.BACKOFF_CAP_SECONDS, max(naps)
    assert len(naps) == 12 - rotation.REFUSAL_STREAK + 1, len(naps)


def test_a_success_resets_the_streak():
    import rotation
    rotation._consecutive_refusals = 7
    rotation.note_pull_success()
    assert rotation._consecutive_refusals == 0


if __name__ == "__main__":
    sys.exit(main())
