"""Pin the rotation invariants (`CHANGES.md` 10, 11, 12).

Three defects came from this module and each cost a run:

  10  a killed worker leaves a RUNNING container, which holds its image, so the
      image cannot be reclaimed until the container is gone
  11  pruning orphaned layers killed the concurrent pull whose containerd lease
      it dropped -- five tasks `unchecked` in under three seconds, with a daemon
      error whose text points nowhere near the cause
  12  a per-task disk budget measured globally, which under concurrency charged
      one worker's image to another and aborted a healthy task

`_docker` is stubbed throughout, so these run with no daemon and no network.

    ~/.venv-fc/bin/python scale/test_rotation.py
"""

import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import rotation  # noqa: E402


class Recorder:
    """Stands in for `_docker`, recording calls and replaying canned output."""

    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def __call__(self, *args, timeout=600):
        self.calls.append(args)
        for prefix, out in self.responses.items():
            if args[:len(prefix)] == prefix:
                return rotation.subprocess.CompletedProcess(
                    args, 0, out, "")
        return rotation.subprocess.CompletedProcess(args, 0, "", "")


def with_stub(responses=None):
    rec = Recorder(responses)
    rotation._docker = rec
    return rec


def restore():
    import importlib
    importlib.reload(rotation)


# --- leases ---------------------------------------------------------------

def test_a_lease_with_a_dead_pid_is_dropped():
    """The crash residue case: the owning process is gone, so the image it was
    holding becomes reclaimable."""
    d = tempfile.mkdtemp()
    try:
        leases = rotation.Leases(d)
        leases.take("swebench/img:latest", "task-a")
        # Rewrite the lease to name a pid that cannot be alive.
        path = leases._path("swebench/img:latest")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        data["pid"] = 2 ** 30
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        assert leases.live_refs() == set()
        assert not os.path.exists(path), "a dead lease must be removed"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_a_live_lease_is_kept():
    d = tempfile.mkdtemp()
    try:
        leases = rotation.Leases(d)
        leases.take("swebench/img:latest", "task-a")
        assert leases.live_refs() == {"swebench/img:latest"}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_a_corrupt_lease_is_removed_not_crashed_on():
    d = tempfile.mkdtemp()
    try:
        leases = rotation.Leases(d)
        with open(os.path.join(d, "junk"), "w", encoding="utf-8") as f:
            f.write("not json")
        assert leases.live_refs() == set()
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- containers before images (CHANGES.md 10) ------------------------------

def test_orphaned_validate_container_is_removed():
    rec = with_stub({("ps",): "validate-formcheck-0-abc\tswebench/img:latest\n"})
    try:
        removed = rotation.reconcile_containers(set())
        assert removed == ["validate-formcheck-0-abc"], removed
        assert ("rm", "-f", "validate-formcheck-0-abc") in rec.calls
    finally:
        restore()


def test_a_live_workers_container_is_protected():
    """Its image is leased, so it must not be touched."""
    with_stub({("ps",): "validate-formcheck-0-abc\tswebench/img:latest\n"})
    try:
        assert rotation.reconcile_containers({"swebench/img:latest"}) == []
    finally:
        restore()


def test_an_unrelated_container_is_never_touched():
    """Matching on verifiers' own `validate-` prefix is what keeps reconcile
    from removing something else on the host."""
    with_stub({("ps",): "someone-elses-db\tpostgres:16\n"})
    try:
        assert rotation.reconcile_containers(set()) == []
    finally:
        restore()


# --- prune vs in-flight pulls (CHANGES.md 11) ------------------------------

def test_prune_is_skipped_while_a_pull_is_in_flight():
    """The bug: `docker image prune` drops the containerd lease an in-flight
    pull is holding, killing it with `lease does not exist`."""
    rec = with_stub()
    try:
        rotation._PULLS_IN_FLIGHT = 1
        assert rotation.prune_is_safe() is False
        assert rotation.reclaim_orphans() == 0
        assert not any(c[:2] == ("image", "prune") for c in rec.calls), rec.calls
    finally:
        rotation._PULLS_IN_FLIGHT = 0
        restore()


def test_prune_runs_when_nothing_is_pulling():
    rec = with_stub()
    try:
        rotation._PULLS_IN_FLIGHT = 0
        rotation.reclaim_orphans()
        assert any(c[:2] == ("image", "prune") for c in rec.calls), rec.calls
    finally:
        restore()


def test_reconcile_does_not_prune_unless_asked():
    """Pruning is opt-in: the normal path prunes once, at run start, before any
    worker exists."""
    rec = with_stub({("ps",): "", ("images",): ""})
    try:
        d = tempfile.mkdtemp()
        rotation.reconcile(rotation.Leases(d))
        assert not any(c[:2] == ("image", "prune") for c in rec.calls), rec.calls
        shutil.rmtree(d, ignore_errors=True)
    finally:
        restore()


# --- worker count and headroom --------------------------------------------

def test_worker_count_is_the_minimum_of_all_bounds():
    """Disk alone suggested 118 on the machine this was written for; RAM and the
    ceiling are what make that a usable number."""
    n = rotation.suggested_workers(budget_bytes=10 ** 15)
    assert 1 <= n <= rotation.MAX_WORKERS, n


def test_worker_count_never_drops_below_one():
    assert rotation.suggested_workers(budget_bytes=1) == 1


def test_headroom_refuses_with_a_reason_naming_the_shortfall():
    original = rotation.free_bytes
    rotation.free_bytes = lambda path=None: 1024
    try:
        rotation.ensure_headroom(need_bytes=4 * 1024 ** 3)
    except rotation.NotEnoughDisk as exc:
        assert "GiB free" in str(exc) and "transport error" in str(exc), exc
    else:
        raise AssertionError("must refuse rather than attempt the pull")
    finally:
        rotation.free_bytes = original


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main():
    failed = 0
    for fn in TESTS:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {fn.__name__}\n        {exc}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
