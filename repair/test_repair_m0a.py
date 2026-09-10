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


# ---------------------------------------------------------------------------
# item 3 -- the overlay surface, and the boundary it is not allowed to cross
# ---------------------------------------------------------------------------

TEST_FILES = ["xarray/tests/test_coding.py"]


def _diff(*paths):
    """A minimal unified diff touching `paths`, enough for `touched_files`."""
    out = []
    for path in paths:
        out += [f"diff --git a/{path} b/{path}",
                f"--- a/{path}", f"+++ b/{path}",
                "@@ -1,1 +1,2 @@", " x = 1", "+# overlay"]
    return "\n".join(out) + "\n"


def test_overlay_accepts_a_file_the_test_patch_touches():
    from container_task import check_tests_overlay
    got = check_tests_overlay(_diff(*TEST_FILES), TEST_FILES, "t")
    assert got == TEST_FILES, got


def test_overlay_refuses_production_python():
    """The one that matters: an overlay reaching a source file could put the
    solution into the tree under the guise of repairing a test, and the 1.0 it
    produced would be indistinguishable from an honest one."""
    from container_task import check_tests_overlay, OverlayScopeError
    prod = "xarray/coding/variables.py"
    try:
        check_tests_overlay(_diff(prod), TEST_FILES + [prod], "t")
    except OverlayScopeError as exc:
        assert "production Python" in str(exc), exc
    else:
        raise AssertionError(
            "an overlay modifying production Python was accepted")


def test_overlay_refuses_a_file_outside_the_test_patch():
    from container_task import check_tests_overlay, OverlayScopeError
    try:
        check_tests_overlay(_diff("xarray/tests/test_other.py"), TEST_FILES, "t")
    except OverlayScopeError as exc:
        assert "does not touch" in str(exc), exc
    else:
        raise AssertionError("an overlay adding a graded file was accepted")


def test_overlay_refuses_a_diff_with_no_readable_scope():
    """Not 'accept it, it changes nothing' -- a diff whose scope cannot be read
    from its own headers is refused, because the check has nothing to check."""
    from container_task import check_tests_overlay, OverlayScopeError
    try:
        check_tests_overlay("no headers here\n", TEST_FILES, "t")
    except OverlayScopeError as exc:
        assert "touches no file" in str(exc), exc
    else:
        raise AssertionError("a headerless overlay was accepted")


def test_build_task_spec_refuses_a_bad_overlay_offline():
    """Before the 4 GiB pull, not after it."""
    from container_task import build_task_spec, OverlayScopeError
    instance = {
        "instance_id": "pydata__xarray-4966", "repo": "pydata/xarray",
        "version": "0.12", "base_commit": "0" * 40,
        "patch": _diff("xarray/coding/variables.py"),
        "test_patch": _diff(*TEST_FILES),
        "problem_statement": "an issue", "FAIL_TO_PASS": "[]",
        "PASS_TO_PASS": "[]",
    }
    spec = build_task_spec(instance, _diff(*TEST_FILES))
    assert spec["tests_overlay"], "a valid overlay did not reach the spec"
    assert build_task_spec(instance)["tests_overlay"] is None

    try:
        build_task_spec(instance, _diff("xarray/coding/variables.py"))
    except OverlayScopeError:
        pass
    else:
        raise AssertionError("build_task_spec accepted a production overlay")


def _reset_task(overlay):
    """A `ContainerFormcheckTask` with `sh` recording instead of executing."""
    from container_task import ContainerFormcheckTask

    class Rec:
        stdout = stderr = ""
        returncode = 0

    task = ContainerFormcheckTask.__new__(ContainerFormcheckTask)
    task.spec = {"tests_overlay": overlay, "test_files": TEST_FILES,
                 "instance_id": "t"}
    task.calls = []
    task.sh = lambda script, check=False: (task.calls.append(script), Rec())[1]
    return task


def test_reset_applies_base_tests_overlay_gold_in_that_order():
    task = _reset_task(_diff(*TEST_FILES))
    task.formcheck_reset()
    applied = [c.split("/")[-1] for c in task.calls if c.startswith("git apply")]
    assert applied == ["tests.diff", "tests_overlay.diff", "gold.diff"], applied


def test_reset_without_an_overlay_is_byte_for_byte_the_old_sequence():
    """The 500-task run must be reproducible: no overlay, no third patch."""
    task = _reset_task(None)
    task.formcheck_reset()
    applied = [c.split("/")[-1] for c in task.calls if c.startswith("git apply")]
    assert applied == ["tests.diff", "gold.diff"], applied


def test_setup_refuses_a_bad_overlay_before_writing_it():
    """A hand-built spec never sees `build_task_spec`, so `setup` re-checks --
    and refuses before the overlay's bytes reach the container."""
    from container_task import ContainerFormcheckTask, OverlayScopeError

    class Rec:
        stdout = "yes"
        stderr = ""
        returncode = 0

    class Info:
        id = "container123"

    class Runtime:
        info = Info()

    prod = "xarray/coding/variables.py"
    task = ContainerFormcheckTask.__new__(ContainerFormcheckTask)
    task.spec = {"gold_diff": "g", "tests_diff": "t",
                 "tests_overlay": _diff(prod),
                 "test_files": TEST_FILES + [prod], "instance_id": "t"}
    task.python = "/usr/bin/python"
    written = []
    task.sh = lambda script, check=False: Rec()
    task.put = lambda path, text: written.append(path)

    try:
        asyncio.run(task.setup(Runtime()))
    except OverlayScopeError:
        pass
    else:
        raise AssertionError("setup accepted a production overlay")
    assert not any("tests_overlay" in w for w in written), written


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
