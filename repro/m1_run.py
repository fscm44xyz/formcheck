"""M1 gate runner: apply the REPAIRED test + each hand-written solution, run
pytest, capture log_m1_<name>.txt. Runs under .venv-pytest.

Solutions (all hand-written):
  gold          -> the PR's gold patch                     (expect PASS  = G1)
  alt           -> M0 correct alternative (no consider_mro) (expect PASS  = G3)
  bug_none      -> no fix at all (pre-patch MRO bug)         (expect FAIL  = G2)
  bug_direct    -> only the class's own marks, bases ignored (expect FAIL  = G2)
  bug_first     -> merge only the FIRST base class's marks   (expect FAIL  = G2)
  bug_dropown   -> MRO but forget the class itself           (expect FAIL  = G2)
"""
import os, sys, subprocess
sys.path.insert(0, os.path.dirname(__file__))
from run_case import REPO, HERE, PY, git, apply_patch, apply_alt, OLD_GUM, STRUCT, assert_editable_pytest

TEST_FILE = os.path.join(REPO, "testing", "test_mark.py")
TEST_CMD_ECHO = "+ pytest -rA testing/test_mark.py"

# ---- the approved repaired test (behavioral, public API) ----
REPAIRED_TEST = '''def test_mark_mro(pytester: Pytester) -> None:
    # Regression test for #10356. The issue's contract is behavioral: a test
    # inheriting from two marked base classes must carry the marks of *both*,
    # rather than one shadowing the other. Assert that observable contract
    # through the public iter_markers() API -- not through the internal
    # get_unpacked_marks() signature, whose private `consider_mro` keyword and
    # exact list order are implementation details the issue never specifies.
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.a
        class A:
            pass

        @pytest.mark.b
        class B:
            pass

        @pytest.mark.c
        class TestC(A, B):
            def test_it(self):
                pass
        """
    )
    items, rec = pytester.inline_genitems()
    (item,) = items
    marker_names = {m.name for m in item.iter_markers()}
    assert marker_names == {"a", "b", "c"}
'''

def apply_repaired_test():
    with open(TEST_FILE, "r", encoding="utf-8") as f:
        src = f.read()
    anchor = "def test_mark_mro() -> None:"
    i = src.index(anchor)
    src = src[:i] + REPAIRED_TEST
    with open(TEST_FILE, "w", encoding="utf-8") as f:
        f.write(src)

# ---- hand-written bad solutions (edits to get_unpacked_marks only) ----
BUG_DIRECT = '''def get_unpacked_marks(obj: object) -> Iterable[Mark]:
    """BAD: only the object's own marks; base classes ignored entirely."""
    if isinstance(obj, type):
        mark_list = list(obj.__dict__.get("pytestmark", []))
    else:
        mark_list = getattr(obj, "pytestmark", [])
        if not isinstance(mark_list, list):
            mark_list = [mark_list]
    return normalize_mark_list(mark_list)'''

BUG_FIRST = '''def get_unpacked_marks(obj: object) -> Iterable[Mark]:
    """BAD: merge only the FIRST base class's marks (ignores siblings)."""
    if isinstance(obj, type):
        mark_list = list(obj.__dict__.get("pytestmark", []))
        if obj.__bases__:
            mark_list += list(obj.__bases__[0].__dict__.get("pytestmark", []))
    else:
        mark_list = getattr(obj, "pytestmark", [])
        if not isinstance(mark_list, list):
            mark_list = [mark_list]
    return normalize_mark_list(mark_list)'''

BUG_DROPOWN = '''def get_unpacked_marks(obj: object) -> Iterable[Mark]:
    """BAD: consider MRO but forget the object's own class (incomplete list)."""
    if isinstance(obj, type):
        mark_list = []
        for klass in obj.__mro__[1:]:
            mark_list += list(klass.__dict__.get("pytestmark", []))
    else:
        mark_list = getattr(obj, "pytestmark", [])
        if not isinstance(mark_list, list):
            mark_list = [mark_list]
    return normalize_mark_list(mark_list)'''

MUTANTS = {"bug_direct": BUG_DIRECT, "bug_first": BUG_FIRST, "bug_dropown": BUG_DROPOWN}

def apply_gum_mutant(new_src):
    with open(STRUCT, "r", encoding="utf-8") as f:
        src = f.read()
    if OLD_GUM not in src:
        raise RuntimeError("mutant anchor not found")
    src = src.replace(OLD_GUM, new_src, 1)
    with open(STRUCT, "w", encoding="utf-8") as f:
        f.write(src)

def apply_solution(name):
    if name == "gold":
        apply_patch(os.path.join(HERE, "gold.diff"))
    elif name == "alt":
        apply_alt()
    elif name == "bug_none":
        pass
    elif name in MUTANTS:
        apply_gum_mutant(MUTANTS[name])
    else:
        raise SystemExit("unknown solution " + name)

def run_one(name):
    git("checkout", "--", ".")
    git("clean", "-fd", "testing", "src")
    apply_patch(os.path.join(HERE, "tests.diff"))
    apply_repaired_test()
    apply_solution(name)
    run = subprocess.run(
        [PY, "-m", "pytest", "-rA", "-p", "no:cacheprovider", "testing/test_mark.py"],
        cwd=REPO, capture_output=True, text=True, timeout=600,
    )
    log = TEST_CMD_ECHO + "\n" + run.stdout + "\n" + run.stderr
    with open(os.path.join(HERE, f"log_m1_{name}.txt"), "w", encoding="utf-8") as f:
        f.write(log)
    git("checkout", "--", ".")
    git("clean", "-fd", "testing", "src")
    tail = [l for l in run.stdout.splitlines() if "passed" in l or "failed" in l or "error" in l]
    print(f"[{name:10s}] exit={run.returncode}  {tail[-1] if tail else '?'}")

if __name__ == "__main__":
    assert_editable_pytest()
    names = sys.argv[1:] or ["gold", "alt", "bug_none", "bug_direct", "bug_first", "bug_dropown"]
    for n in names:
        run_one(n)
