"""Pin D2: a digest that collapses turns every transform into a false CLEAN.

D2 was `_tree_digest` running `sha256sum <paths> 2>/dev/null || true`. Any
failure of that command sends its diagnostics to stderr (suppressed) and leaves
stdout EMPTY, so the digest was the hash of the empty string -- identical for
every tree.

The graded result is memoized on that digest, so the consequence is not "one
wrong row". It is:

    control run      -> pytest on the reference solution -> memo[K] = reward 1.0
    transform applied
    oracle asks      -> same K -> MEMO HIT -> reward 1.0, p2p_fail 0 -> preserved
    hook re-grades   -> same K -> MEMO HIT -> reward 1.0 -> CLEAN

Every judged transform on that task comes back CLEAN and the task reports no
witness. A false CLEAN is invisible in results -- it looks exactly like a task
whose reward is not form-coupled -- and it biases THE NUMBER downward, which is
the direction nobody audits.

`test_collapse_makes_everything_clean` reproduces that end to end against the
real `FormCheckMixin`, so the blast radius is a measured property rather than an
argument. The rest pin the fix.

    ~/.venv-fc/bin/python scale/test_digest.py
"""

import asyncio
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "repro"))

from container_task import SweBenchFormcheckTask  # noqa: E402


class FakeCompleted:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def make_task(sh_impl, targets=("a.py", "b.py"), test_files=()):
    """A `SweBenchFormcheckTask` with `sh` stubbed and nothing else touched.

    Constructed without `__init__` so the test needs no dataset row; only the
    attributes `_tree_digest` actually reads are set.

    `test_files` defaults to empty so the four tests that pin D2 keep asserting
    against two paths, exactly as they did before repair-M0a widened the digest.
    """
    task = SweBenchFormcheckTask.__new__(SweBenchFormcheckTask)
    task.FORMCHECK_TARGETS = tuple(targets)
    task.spec = {"test_files": tuple(test_files)}
    task._graded_memo = {}
    task.sh = sh_impl
    return task


def fake_tree_sh(files):
    """An `sh` that answers the digest script the way a container would.

    It reads the paths OUT OF THE SCRIPT rather than being handed them, so a
    path the implementation never asks about is a path that never reaches the
    digest. That is what makes the two tests below regression tests rather than
    restatements of the fix: before repair-M0a the script names only the
    production targets, so two trees differing only in a graded test file hash
    identically and the difference is invisible.
    """
    def sh(script):
        out = []
        for path in re.findall(r"\[ -f '([^']+)' \]", script):
            if path in files:
                digest = hashlib.sha256(files[path].encode()).hexdigest()
                out.append(f"{digest}  {path}")
            else:
                out.append(f"MISSING {path}")
        return FakeCompleted(("\n".join(out) + "\n") if out else "")
    return sh


class FakeRuntime:
    """`runtime.run` recorded, so "did the graded suite actually re-run?" is a
    measured fact and not an inference from a reward that happens to match."""

    def __init__(self, stdout):
        self.stdout = stdout
        self.calls = []

    async def run(self, argv, env):
        self.calls.append(argv)
        return FakeCompleted(self.stdout, "")


def test_digest_varies_with_content():
    """The whole point: two different trees, two different digests."""
    def sh_a(script):
        return FakeCompleted("aaa  a.py\nbbb  b.py\n")

    def sh_b(script):
        return FakeCompleted("aaa  a.py\nZZZ  b.py\n")

    assert make_task(sh_a)._tree_digest() != make_task(sh_b)._tree_digest()


def test_missing_binary_raises_instead_of_collapsing():
    """`sha256sum` absent -> shell writes to stderr, stdout empty.

    This is the condition that made D2 dangerous, because it is a property of
    the IMAGE, so it would hold for every task from that repo and silently make
    all of them CLEAN.
    """
    def sh(script):
        return FakeCompleted("", "sh: sha256sum: not found", 127)

    try:
        make_task(sh)._tree_digest()
    except RuntimeError as exc:
        assert "expected 2 line(s), got 0" in str(exc), exc
    else:
        raise AssertionError("empty output must raise, never return a digest")


def test_partial_output_raises():
    """One file hashed, one silently dropped, is still a collision risk."""
    def sh(script):
        return FakeCompleted("aaa  a.py\n")

    try:
        make_task(sh)._tree_digest()
    except RuntimeError as exc:
        assert "expected 2 line(s), got 1" in str(exc), exc
    else:
        raise AssertionError("partial output must raise")


def test_all_targets_missing_raises():
    """Well-formed but degenerate: identical for any all-missing tree."""
    def sh(script):
        return FakeCompleted("MISSING a.py\nMISSING b.py\n")

    try:
        make_task(sh)._tree_digest()
    except RuntimeError as exc:
        assert "every digested path is missing" in str(exc), exc
    else:
        raise AssertionError("an all-missing tree must raise")


def test_one_missing_one_present_is_fine_and_distinct():
    """A genuinely absent target is recorded, not ignored -- and still
    distinguishes trees that differ in the file that IS there."""
    def sh_a(script):
        return FakeCompleted("MISSING a.py\nbbb  b.py\n")

    def sh_b(script):
        return FakeCompleted("MISSING a.py\nZZZ  b.py\n")

    da, db = make_task(sh_a)._tree_digest(), make_task(sh_b)._tree_digest()
    assert da and db and da != db


def test_collapse_makes_everything_clean():
    """THE BLAST RADIUS, measured against the real hook.

    A task whose digest is constant is driven through `FormCheckMixin.formcheck`
    with a transform that genuinely changes the tree and a reward function that
    would score it 0.0. With the memo keyed on a collapsed digest, the graded
    call never re-runs: every verdict comes back CLEAN and no witness is
    reported. This is what D2 would have produced, and what a results file
    cannot reveal.
    """
    from formcheck_hook import FormCheckMixin

    class Op:
        id, tier, observable = "symbol_rename", "MEDIUM", "symbol identity"
        loud_failure = True

        def anchors(self, sources, target, issue):
            return [{"label": "sym", "name": "sym"}]

        def apply(self, sources, target, anchor, issue):
            new = dict(sources)
            new[target] = sources[target].replace("sym", "renamed")
            return new, {"operator": self.id, "tier": self.tier,
                         "observable": self.observable, "anchor": "sym",
                         "name": "sym", "loud_failure": True}

    class Task(FormCheckMixin):
        FORMCHECK_TARGETS = ("a.py",)

        def __init__(self, collapsed):
            self.collapsed = collapsed
            self.tree = {"a.py": "def sym(): pass"}
            self.memo = {}

        def formcheck_issue(self):
            return "an issue naming nothing"

        def formcheck_reset(self):
            self.tree = {"a.py": "def sym(): pass"}

        def formcheck_read(self):
            return dict(self.tree)

        def formcheck_write(self, sources):
            self.tree = dict(sources)

        def digest(self):
            # The bug, exactly: a constant when the command fails.
            return "CONSTANT" if self.collapsed else hashlib.sha256(
                self.tree["a.py"].encode()).hexdigest()

        async def formcheck_graded(self, runtime):
            key = self.digest()
            if key not in self.memo:
                # The reward rejects the rename: a real witness.
                reward = 1.0 if "sym" in self.tree["a.py"] else 0.0
                self.memo = {key: ("log", reward)}
            self.graded = {"p2p_fail": 0, "f2p_fail": 0,
                           "p2p_failing": [], "f2p_failing": []}
            return self.memo[key]

        async def formcheck_oracle(self, runtime, report=None):
            return True, {report["observable"]: True}

    import formcheck_hook
    original = formcheck_hook.FAMILY
    formcheck_hook.FAMILY = [Op()]
    try:
        broken = Task(collapsed=True)
        asyncio.run(broken.formcheck(None))
        verdicts_broken = [v for lbl, v, _why in broken.formcheck_log
                           if lbl != "<control>"]

        working = Task(collapsed=False)
        asyncio.run(working.formcheck(None))
        verdicts_ok = [v for lbl, v, _why in working.formcheck_log
                       if lbl != "<control>"]
    finally:
        formcheck_hook.FAMILY = original

    assert verdicts_broken == ["CLEAN"], verdicts_broken
    assert verdicts_ok == ["WITNESS"], verdicts_ok
    assert verdicts_broken != verdicts_ok, (
        "the collapsed digest must demonstrably change the verdict, or this "
        "test proves nothing")


def test_digest_varies_with_the_graded_test_files():
    """repair-M0a: same production targets, DIFFERENT graded test file.

    `_tree_digest` hashed only `FORMCHECK_TARGETS`, on the stated ground that
    "only the targets are ever modified". That was true of every transform in
    the detection family -- and it stops being true the moment a test-side
    overlay exists, because an overlay by construction changes no target. The
    digest would then be identical across the overlaid and un-overlaid trees,
    and `graded_report` would serve the un-overlaid grading for the overlaid
    one.

    Same shape as D2 and as the nine defects of `REPORT.md` 7: a check
    reporting a verdict for a reason invisible in its own output. The reward
    would read 1.0 because the overlay was never graded, and nothing in the
    record would say so.
    """
    prod = {"a.py": "def sym(): pass", "b.py": "x = 1"}
    test_path = "xarray/tests/test_coding.py"
    plain = dict(prod, **{test_path: "def test_x():\n    assert True\n"})
    overlaid = dict(prod, **{test_path: "# overlay\ndef test_x():\n    assert True\n"})

    a = make_task(fake_tree_sh(plain), test_files=(test_path,))
    b = make_task(fake_tree_sh(overlaid), test_files=(test_path,))

    assert a._tree_digest() != b._tree_digest(), (
        "two trees whose graded test file differs produced the SAME digest -- "
        "a test-side overlay is invisible to the graded memo")


def test_memo_re_runs_when_only_the_test_file_changed():
    """THE BLAST RADIUS, through the real `graded_report`.

    Three gradings on one task: the plain tree, the same tree with the graded
    test file overlaid, then the overlaid tree again. The middle one must
    actually re-run the suite, and the third must still be served from the memo
    -- widening the digest must not degrade into "never memoize", which would
    double the container time of all 500 tasks.

    `runtime.run` calls are counted rather than inferred from the reward: both
    gradings return the same reward here, so the reward cannot distinguish a
    re-run from a memo hit. That is precisely why D2 was invisible.
    """
    fixture = json.load(open(os.path.join(HERE, "fixtures",
                                          "xarray_4966_rename.json")))
    # The fixture's first line is the echoed command; `graded_report` writes its
    # own, so hand the runtime only the body.
    body = fixture["log"].split("\n", 1)[1]

    test_path = "xarray/tests/test_coding.py"
    target = "xarray/coding/variables.py"
    files = {target: "class UnsignedIntegerCoder: pass\n",
             test_path: "def test_x():\n    assert True\n"}

    task = SweBenchFormcheckTask.__new__(SweBenchFormcheckTask)
    task.FORMCHECK_TARGETS = (target,)
    task.meta = {"instance_id": "pydata__xarray-4966", "repo": "pydata/xarray",
                 "version": "0.12",
                 "FAIL_TO_PASS": fixture["graded"]["f2p_failing"],
                 "PASS_TO_PASS": fixture["graded"]["p2p_failing"]}
    task.spec = {"test_files": (test_path,),
                 "tests_diff": f"diff --git a/{test_path} b/{test_path}\n"}
    task.python = "/opt/miniconda3/envs/testbed/bin/python"
    task._graded_memo = {}
    task.digest_trace = []
    task.last_digest = None
    task.sh = fake_tree_sh(files)

    runtime = FakeRuntime(body)

    asyncio.run(task.graded_report(runtime))
    assert len(runtime.calls) == 1, runtime.calls
    assert task.digest_trace[0]["memo_hit"] is False

    # The overlay: the graded test file changes, no target does.
    files[test_path] = "# overlay\n" + files[test_path]
    asyncio.run(task.graded_report(runtime))
    assert task.digest_trace[1]["digest"] != task.digest_trace[0]["digest"], (
        "the overlaid tree hashed to the control's digest")
    assert task.digest_trace[1]["memo_hit"] is False, (
        "the overlaid tree was graded from the un-overlaid tree's memo")
    assert len(runtime.calls) == 2, (
        f"the graded suite did not re-run after the overlay: {runtime.calls}")

    # Unchanged tree: the memo must still work.
    asyncio.run(task.graded_report(runtime))
    assert task.digest_trace[2]["memo_hit"] is True, (
        "widening the digest must not disable memoization")
    assert len(runtime.calls) == 2, runtime.calls


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
