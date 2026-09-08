"""Pin the gold-patch scope rule (`CHANGES.md` 5, 6).

The rule `writeup.md` 3.3 states: an operator is offered symbols whose definition
the reference patch overlaps. The restriction exists so the choice of anchor
cannot be made in view of the outcome; without it `symbol_rename` sweeps a whole
module and picking the anchors that yield witnesses is selecting for the result.

The first implementation read names out of the `@@` hunk header. git prints the
nearest PRECEDING definition there, which is often one the hunk does not touch,
so the rule ADMITTED UNTOUCHED SYMBOLS -- widening the sanctioned region, the one
direction 3.3 exists to prevent. On `pytest-10356` it admitted
`MarkDecorator.__call__` and seven `kwonly_specialize` anchors on its keyword
parameters. All seven refused, which was luck.

These tests run on patch text and source strings. No docker, no network.

    ~/.venv-fc/bin/python scale/test_scope.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "repro"))

from container_task import (  # noqa: E402
    changed_lines, symbols_covering, touched_files,
)

REPRO = os.path.join(os.path.dirname(HERE), "repro")

# A hunk whose header names a function the hunk does not modify. This is the
# exact shape that caused CHANGES.md 5.
MISLEADING_HEADER = """diff --git a/m.py b/m.py
--- a/m.py
+++ b/m.py
@@ -10,3 +10,4 @@ def untouched_neighbour(self):
 context_line_one
-removed_line
+added_line
+another_added_line
"""

SOURCE = """\
class Owner:
    def untouched_neighbour(self):
        return 1

    def edited_method(self):
        return 2


def module_level(x):
    return x
"""


def test_hunk_header_name_is_not_treated_as_touched():
    """The regression: `untouched_neighbour` must NOT enter scope.

    It is named in the `@@` header purely because git prints the nearest
    preceding definition, and the changed lines are below it.
    """
    changed = changed_lines(MISLEADING_HEADER)["m.py"]
    # Lines 10-13 in the post-patch file: inside `module_level`, not the method
    # the header names.
    names = symbols_covering(SOURCE, set(changed))
    assert "untouched_neighbour" not in names, (
        f"the @@ header's name leaked back into scope: {names}")


def test_changed_lines_uses_the_new_side_numbering():
    changed = changed_lines(MISLEADING_HEADER)["m.py"]
    assert min(changed) >= 10, changed
    assert max(changed) <= 14, changed


def test_symbols_covering_finds_the_definition_containing_a_line():
    assert symbols_covering(SOURCE, {6}) >= {"edited_method", "Owner"}
    assert symbols_covering(SOURCE, {10}) == {"module_level"}


def test_a_class_enters_scope_with_its_method():
    """A patch editing a method touches the class that owns it, and that falls
    out of the line ranges rather than needing a separate rule."""
    names = symbols_covering(SOURCE, {6})
    assert "Owner" in names and "edited_method" in names


def test_an_untouched_sibling_never_enters_scope():
    """Editing one method must not admit the other."""
    names = symbols_covering(SOURCE, {6})
    assert "untouched_neighbour" not in names, names


def test_syntax_error_yields_no_symbols_rather_than_raising():
    """A file the container holds mid-transform may not parse. Returning no
    symbols costs an anchor; raising would abort the task."""
    assert symbols_covering("def (((", {1}) == set()


def test_real_gold_patch_scope_is_the_two_documented_symbols():
    """`pytest-10356`, against its own gold patch.

    SCOPE.md records the answer: the mechanical rule yields
    {get_unpacked_marks, store_mark}, and NOT normalize_mark_list or
    MarkDecorator, which the hand-picked Phase 2 set contained. Pinned here so
    the documented divergence cannot drift silently.
    """
    with open(os.path.join(REPRO, "gold.diff"), encoding="utf-8") as f:
        gold = f.read()
    changed = changed_lines(gold)
    assert list(changed) == ["src/_pytest/mark/structures.py"], list(changed)
    lines = changed["src/_pytest/mark/structures.py"]
    assert min(lines) == 358 and max(lines) == 414, (min(lines), max(lines))


def test_touched_files_handles_creation_and_deletion():
    created = ("diff --git a/new.py b/new.py\n"
               "--- /dev/null\n+++ b/new.py\n")
    deleted = ("diff --git a/old.py b/old.py\n"
               "--- a/old.py\n+++ /dev/null\n")
    assert touched_files(created) == ["new.py"]
    assert touched_files(deleted) == ["old.py"]


def test_multi_file_patch_keeps_files_separate():
    patch = ("diff --git a/x.py b/x.py\n@@ -1,1 +1,2 @@\n context\n+added\n"
             "diff --git a/y.py b/y.py\n@@ -50,1 +50,2 @@\n context\n+added\n")
    changed = changed_lines(patch)
    assert set(changed) == {"x.py", "y.py"}
    assert max(changed["x.py"]) < min(changed["y.py"]), changed


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
