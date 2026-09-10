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
import json
import os
import re
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


# ---------------------------------------------------------------------------
# addendum -- the overlay's POSITIVE and NEGATIVE control, kept as a pair
# ---------------------------------------------------------------------------
#
# A no-op overlay cannot distinguish "the overlay reached the graded run" from
# "the overlay was silently dropped": both leave the reward at 1.0. The digest
# narrows it -- `_tree_digest` shells out to `sha256sum` INSIDE the container, so
# a moved digest means the bytes in /testbed really changed -- but it still does
# not establish that the graded run EXECUTED those bytes. A stale `.pyc`, a
# directive pointing at another file, or a collection that never reached the
# module would all move the digest and change nothing that pytest ran.
#
# Only a falsifiable positive control closes that: an overlay that must break a
# named set of tests, and does, in the graded log, by its own message.
#
# THE TWO ARE KEPT TOGETHER ON PURPOSE. The positive control alone proves the
# overlay can reach the graded run but says nothing about whether an inert one
# perturbs it; the no-op alone proves nothing at all. `test_the_control_pair_is_
# intact` fails if either record goes missing, so the pair cannot be quietly
# halved.
#
# The records are committed artifacts of container runs, so these tests are
# offline and fast. Regenerate with:
#
#   ~/.venv-fc/bin/python scale/run.py --instance-id pydata__xarray-4966 \
#       --records-dir repair/records_m0a/plain
#   ~/.venv-fc/bin/python scale/run.py --instance-id pydata__xarray-4966 \
#       --tests-overlay repair/overlay_positive_xarray_4966.diff \
#       --records-dir repair/records_m0a/positive
#   ~/.venv-fc/bin/python scale/run.py --instance-id pydata__xarray-4966 \
#       --tests-overlay repair/overlay_noop_xarray_4966.diff \
#       --records-dir repair/records_m0a/noop_rerun

RECORDS = os.path.join(HERE, "records_m0a")
INSTANCE = "pydata__xarray-4966.json"

# The four the positive overlay targets. Written out rather than derived, so a
# change to which tests are hit shows up here as a diff.
TARGETED = {f"xarray/tests/test_coding.py::test_decode_unsigned_from_signed[{b}]"
            for b in (1, 2, 4, 8)}
# The four that must be untouched: same file, same module, adjacent function.
UNTOUCHED = {f"xarray/tests/test_coding.py::test_decode_signed_from_unsigned[{b}]"
             for b in (1, 2, 4, 8)}
OVERLAY_MESSAGE = "AssertionError: overlay landed"


def _record(name):
    path = os.path.join(RECORDS, name, INSTANCE)
    assert os.path.exists(path), (
        f"missing control record {path} -- regenerate it with the command in "
        "this file's header. A missing record must FAIL, not skip: a control "
        "that silently stops running is the defect this pair exists to catch.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _states(log):
    """Per-node-id outcome, from pytest's own `-rA` summary lines."""
    out = {}
    for line in log.splitlines():
        m = re.match(r"^(PASSED|FAILED|ERROR)\s+(\S+)", line.strip())
        if m:
            out[m.group(2)] = m.group(1)
    return out


def test_the_control_pair_is_intact():
    """Neither half may be dropped. The negative alone proves nothing."""
    for name in ("plain", "positive", "noop_rerun"):
        rec = _record(name)
        assert rec["instance_id"] == "pydata__xarray-4966", rec["instance_id"]
        assert rec["error"] is None, rec["error"]
        assert rec["completed"] is True


def test_baseline_scores_one_with_no_overlay():
    """The reference point both controls are read against."""
    rec = _record("plain")
    assert rec["control"]["passed"] is True, rec["control"]
    assert "scores 1.0" in rec["control"]["reason"], rec["control"]["reason"]


def test_positive_control_drops_the_reward():
    """POSITIVE: an overlay that must break the graded run, and does.

    Read against the ORIGINAL gold: `control` is the untransformed reference
    solution, so this is the reward of the real solution against the overlaid
    suite, with no transform anywhere in it.
    """
    rec = _record("positive")
    control = rec["control"]
    assert control["passed"] is False, "the breaking overlay left the reward at 1.0"
    assert control["graded"]["reward"] == 0.0, control["graded"]["reward"]


def test_positive_control_fails_exactly_the_targeted_node_ids():
    """SCOPE: the four targeted fail, the four adjacent pass, nothing else moves.

    The baseline state of every graded test is PASSED -- not assumed, derived:
    the un-overlaid control scored 1.0, and `get_resolution_status` returns FULL
    only when every FAIL_TO_PASS and every PASS_TO_PASS succeeded.
    """
    assert _record("plain")["control"]["passed"] is True
    control = _record("positive")["control"]
    graded, states = control["graded"], _states(control["log"] or "")

    assert len(states) == 25, f"expected 25 graded node ids, got {len(states)}"
    assert graded["p2p_fail"] == 4 and graded["p2p_pass"] == 17, graded
    assert graded["f2p_fail"] == 0 and graded["f2p_pass"] == 4, graded

    failed = {t for t, st in states.items() if st != "PASSED"}
    assert failed == TARGETED, (
        "the overlay is not scoped the way the contract claims -- changed "
        f"state: {sorted(failed)}, expected exactly {sorted(TARGETED)}")
    for node in UNTOUCHED:
        assert states.get(node) == "PASSED", (node, states.get(node))


def test_positive_control_message_is_verbatim_in_the_graded_log():
    """The overlay's own text, in the log, four times -- one per parametrization.

    Matching the message rather than merely counting failures is what ties the
    failure to THIS overlay: any breakage would drop the reward, only this one
    says `overlay landed`.
    """
    log = _record("positive")["control"]["log"] or ""
    assert OVERLAY_MESSAGE in log, "the overlay's message is not in the graded log"
    assert log.count(OVERLAY_MESSAGE) == len(TARGETED), log.count(OVERLAY_MESSAGE)


def test_noop_control_keeps_the_reward_at_one():
    """NEGATIVE: the same surface, an inert overlay, reward unchanged.

    Same file, same application point, same everything except the content -- so
    the drop in the positive control is attributable to what the overlay says,
    not to the fact that an overlay was applied at all.
    """
    rec = _record("noop_rerun")
    assert rec["control"]["passed"] is True, rec["control"]
    assert "scores 1.0" in rec["control"]["reason"], rec["control"]["reason"]
    verdicts = [(lbl, v) for lbl, v, _ in rec["log"]]
    assert ("symbol_rename:UnsignedIntegerCoder", "WITNESS") in verdicts, verdicts


def test_the_three_trees_have_three_distinct_digests():
    """No overlay, inert overlay, breaking overlay: three different trees.

    Computed container-side (`docker exec sha256sum`), so this is a statement
    about the bytes in /testbed rather than about the spec the host built.
    """
    seen = {name: _record(name)["digest_trace"][0]["digest"]
            for name in ("plain", "noop_rerun", "positive")}
    assert len(set(seen.values())) == 3, seen


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
