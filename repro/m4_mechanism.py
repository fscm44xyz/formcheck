"""Confirm H_dup survives by the PREDICTED mechanism: iter_markers() yields a
duplicated marker, but the set of names is insensitive to duplicates so the
repaired test's set-equality passes. Runs under .venv-pytest."""
import os, sys, subprocess, tempfile, shutil
sys.path.insert(0, os.path.dirname(__file__))
import run_case
from m4_mutants import HELDOUT

PROBE = '''import pytest

@pytest.mark.a
class A: pass
@pytest.mark.b
class B: pass
@pytest.mark.c
class TestC(A, B):
    def test_it(self):
        assert True
'''
CONFTEST = '''def pytest_collection_modifyitems(items):
    for item in items:
        if item.name == "test_it":
            names_list = [m.name for m in item.iter_markers()]
            with open(item.config.rootpath / "markers.txt", "w") as f:
                f.write(",".join(names_list))
'''

def apply_gold_plus_dup():
    run_case.git("checkout", "--", ".")
    run_case.git("clean", "-fd", "testing", "src")
    run_case.apply_patch(os.path.join(run_case.HERE, "gold.diff"))
    m = HELDOUT["H_dup"]
    with open(run_case.STRUCT, encoding="utf-8") as f:
        src = f.read()
    src = src.replace(m["old"], m["new"], 1)
    with open(run_case.STRUCT, "w", encoding="utf-8") as f:
        f.write(src)

def main():
    apply_gold_plus_dup()
    proj = tempfile.mkdtemp(prefix="h_dup_")
    try:
        open(os.path.join(proj, "test_repro.py"), "w").write(PROBE)
        open(os.path.join(proj, "conftest.py"), "w").write(CONFTEST)
        subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q",
                        "--no-header", "-o", "addopts=", proj],
                       cwd=proj, capture_output=True, text=True, timeout=300)
        raw = open(os.path.join(proj, "markers.txt")).read()
    finally:
        shutil.rmtree(proj, ignore_errors=True)
        run_case.git("checkout", "--", ".")
        run_case.git("clean", "-fd", "testing", "src")

    names_list = raw.split(",")
    from collections import Counter
    counts = Counter(names_list)
    print("Under H_dup (gold with consider_mro flipped False->True):")
    print(f"  iter_markers() name LIST : {names_list}")
    print(f"  per-name counts          : {dict(counts)}")
    print(f"  name SET                 : {set(names_list)}")
    dup = [n for n, c in counts.items() if c > 1]
    print(f"\n  duplicated marker(s)     : {dup}")
    print(f"  repaired assert (set==)  : {set(names_list) == {'a','b','c'}}  "
          f"-> {'PASSES (survives)' if set(names_list) == {'a','b','c'} else 'FAILS'}")
    print("\nMechanism confirmed: duplication is present in the LIST, invisible to the SET."
          if dup and set(names_list) == {'a', 'b', 'c'}
          else "\nMechanism NOT as predicted -- investigate.")

if __name__ == "__main__":
    main()
