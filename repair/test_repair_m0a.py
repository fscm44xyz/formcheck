"""repair-M0a: the transform is persisted, and the overlay cannot reach production.

Two milestone invariants, each pinned against the real object rather than a
restatement of it.

    item 2   `_formcheck_row` records `report["detail"]` and leaves the twelve
             keys every existing record and `scale/aggregate.py` already read
             untouched. Both halves matter: adding the key is the fix, and NOT
             renaming the other twelve is what keeps 500 written records
             readable.

    item 3   the test-side overlay may only modify files the task's own test
             patch already names. This is asserted in `container_task`, not
             documented, because an overlay that reaches a production file would
             let a "repaired test" smuggle in a solution -- and the resulting
             1.0 would be indistinguishable from an honest one.

    ~/.venv-fc/bin/python repair/test_repair_m0a.py
"""

import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scale"))
sys.path.insert(0, os.path.join(ROOT, "repro"))

# The twelve keys as they stood before repair-M0a. Written out rather than
# computed, so a rename shows up here as a diff instead of being absorbed.
TWELVE = ("operator", "tier", "file", "anchor", "verdict", "reason",
          "observable", "loud_failure", "graded_log", "graded_report",
          "failure_analysis", "tree_digest")

DETAIL = {"new_name": "sym__renamed", "references_rewritten": 3,
          "files": ["a.py", "b.py"]}


def run_hook():
    """Drive the real `FormCheckMixin.formcheck` over one applying operator and
    one that finds no anchor, and return the rows it built."""
    from formcheck_hook import FormCheckMixin
    import formcheck_hook

    class Applying:
        id, tier, observable = "symbol_rename", "MEDIUM", "symbol identity"
        loud_failure = True

        def anchors(self, sources, target, issue):
            return [{"label": "sym", "name": "sym"}]

        def apply(self, sources, target, anchor, issue):
            new = dict(sources)
            new[target] = sources[target].replace("sym", "renamed")
            return new, {"operator": self.id, "tier": self.tier,
                         "observable": self.observable, "anchor": "sym",
                         "name": "sym", "loud_failure": True,
                         "detail": dict(DETAIL)}

    class NoAnchor:
        id, tier, observable = "message_reword", "MEDIUM", "exception message"
        loud_failure = False

        def anchors(self, sources, target, issue):
            return []

    class Task(FormCheckMixin):
        FORMCHECK_TARGETS = ("a.py",)

        def __init__(self):
            self.tree = {"a.py": "def sym(): pass"}

        def formcheck_issue(self):
            return "an issue naming nothing"

        def formcheck_reset(self):
            self.tree = {"a.py": "def sym(): pass"}

        def formcheck_read(self):
            return dict(self.tree)

        def formcheck_write(self, sources):
            self.tree = dict(sources)

        async def formcheck_graded(self, runtime):
            self.graded = {"p2p_fail": 0, "f2p_fail": 0,
                           "p2p_failing": [], "f2p_failing": []}
            return "log", 1.0 if "sym" in self.tree["a.py"] else 0.0

        async def formcheck_oracle(self, runtime, report=None):
            return True, {report["observable"]: True}

    original = formcheck_hook.FAMILY
    formcheck_hook.FAMILY = [Applying(), NoAnchor()]
    try:
        task = Task()
        asyncio.run(task.formcheck(None))
        return task.formcheck_rows
    finally:
        formcheck_hook.FAMILY = original


def test_the_twelve_keys_are_untouched():
    """A record written before repair-M0a must still parse the same way."""
    for row in run_hook():
        missing = [k for k in TWELVE if k not in row]
        assert not missing, f"key(s) dropped or renamed: {missing}"


def test_row_carries_exactly_one_new_key():
    """Thirteen, not fourteen: the milestone adds `detail` and nothing else."""
    for row in run_hook():
        extra = sorted(set(row) - set(TWELVE))
        assert extra == ["detail"], f"unexpected key(s) on the row: {extra}"


def test_detail_is_persisted_verbatim():
    """The applying operator's own object, not a summary of it.

    Verbatim because the shape is per-operator: four operators write four
    different `detail` dicts, and a normalisation step here would be this file
    inventing a schema for objects it does not own.
    """
    rows = run_hook()
    applied = [r for r in rows if r["verdict"] == "WITNESS"]
    assert applied, [r["verdict"] for r in rows]
    # `.get`, so a missing key fails as an assertion rather than a KeyError
    # traceback -- existence is pinned by `test_row_carries_exactly_one_new_key`.
    assert applied[0].get("detail") == DETAIL, applied[0].get("detail")


def test_detail_is_none_when_no_transform_was_applied():
    """NOT_APPLICABLE and REFUSED never reach `apply`, so there is no transform.

    Recorded as absent rather than as an empty dict: `{}` would read as "a
    transform that changed nothing", which is a different claim.
    """
    rows = run_hook()
    na = [r for r in rows if r["verdict"] == "NOT_APPLICABLE"]
    assert na, [r["verdict"] for r in rows]
    for row in na:
        assert row.get("detail") is None, row.get("detail")


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
