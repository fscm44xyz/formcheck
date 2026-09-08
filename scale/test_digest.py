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
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "repro"))

from container_task import SweBenchFormcheckTask  # noqa: E402


class FakeCompleted:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def make_task(sh_impl, targets=("a.py", "b.py")):
    """A `SweBenchFormcheckTask` with `sh` stubbed and nothing else touched.

    Constructed without `__init__` so the test needs no dataset row; only the
    attributes `_tree_digest` actually reads are set.
    """
    task = SweBenchFormcheckTask.__new__(SweBenchFormcheckTask)
    task.FORMCHECK_TARGETS = tuple(targets)
    task._graded_memo = {}
    task.sh = sh_impl
    return task


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
        assert "every target is missing" in str(exc), exc
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
