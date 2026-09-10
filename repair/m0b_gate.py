"""repair-M0b: does the repaired test remove the coupling WITHOUT hollowing out?

Two conditions, both executable, both required. Neither is sufficient alone --
a test that asserts nothing passes the first and fails the second, and the
original coupled test passes the second and fails the first.

  C1  the RENAMED gold scores 1.0        the coupling is gone
  C2  a genuinely broken solution scores 0.0   the test still discriminates

C2's breakage must be BEHAVIOURAL with names intact. A mutant that breaks an
import or renames the class would fail the repaired test for the same coupled
reason as before, and would prove nothing about behaviour -- it would only
re-measure the defect being repaired. So every mutant here edits an expression
inside the gold's own fix region and touches no identifier, no import and no
class name.

The matrix is run for BOTH the original and the repaired test, because "the
repair did not weaken detection" is a comparison, not an absolute: a mutant the
original test also missed says nothing about the repair.

Grading is `repro/m4_grader.grade_log` -- the same offline SWE-bench-format
grader the 500-task run used, over the same FAIL_TO_PASS / PASS_TO_PASS lists.
No verdict here is eyeballed from pytest output.

    ~/.venv-fc/bin/python repair/m0b_gate.py
    ~/.venv-fc/bin/python repair/m0b_gate.py --keep-image   # skip the re-pull
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scale"))
sys.path.insert(0, os.path.join(ROOT, "repro"))

from container_task import build_task_spec, check_tests_overlay  # noqa: E402
from m4_grader import grade_log  # noqa: E402

INSTANCE_ID = "pydata__xarray-4966"
IMAGE = "swebench/sweb.eval.x86_64.pydata_1776_xarray-4966:latest"
CONTAINER = "repair-m0b-gate"
WORKDIR = "/testbed"
PY = "/opt/miniconda3/envs/testbed/bin/python"
TARGET = "xarray/coding/variables.py"
REPAIR_DIFF = os.path.join(HERE, "overlay_repair_xarray_4966.diff")
OUT = os.path.join(HERE, "m0b_gate_result.json")

# The alpha-rename `symbol_rename` produced as the witness: the anchor plus every
# production reference. Applied as an explicit edit list rather than by importing
# the operator, so the mutant matrix and the rename are delivered by one
# mechanism and a failure here cannot be an operator-plumbing failure.
RENAME = ("UnsignedIntegerCoder", "UnsignedIntegerCoder__renamed",
          [TARGET, "xarray/conventions.py"])

# BEHAVIOURAL mutants. Each is an exact string edit inside the gold's own added
# branch. None renames anything, none touches an import: the symbol, the class
# and every reference survive untouched, so a failure is a failure of behaviour.
MUTANTS = {
    "bug_noop": {
        "old": "                    data = lazy_elemwise_func(data, transform, signed_dtype)",
        "new": "                    data = data",
        "effect": "the signed view is computed and then never applied",
    },
    "bug_width": {
        "old": '                    signed_dtype = np.dtype("i%s" % data.dtype.itemsize)',
        "new": '                    signed_dtype = np.dtype("i1")',
        "effect": "converts to int8 regardless of width -- correct only at bits=1",
    },
    "bug_condflip": {
        "old": '                if unsigned == "false":',
        "new": '                if unsigned == "true":',
        "effect": "the added branch never fires for the case the issue describes",
    },
}

SOLUTIONS = ["gold", "gold_renamed"] + list(MUTANTS)
TESTS = ["original", "repaired"]


def sh(script, check=False):
    r = subprocess.run(
        ["docker", "exec", "--workdir", WORKDIR, CONTAINER, "sh", "-c", script],
        capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{script[:90]!r} -> {r.stderr.strip()[:300]}")
    return r


def put(path, text):
    r = subprocess.run(
        ["docker", "exec", "-i", "--workdir", WORKDIR, CONTAINER,
         "sh", "-c", f"mkdir -p $(dirname '{path}') && cat > '{path}'"],
        input=text, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"put {path}: {r.stderr.strip()[:300]}")


def edit(path, old, new, what):
    """Exact single replacement in a container file, or raise.

    Never a silent no-op: an anchor that has drifted must stop the gate, not
    produce a 'mutant' identical to the gold that then reports itself CAUGHT.
    """
    src = sh(f"cat '{path}'", check=True).stdout
    if src.count(old) != 1:
        raise RuntimeError(
            f"{what}: anchor appears {src.count(old)} time(s) in {path}, "
            f"expected exactly 1 -- refusing to apply an edit whose effect "
            f"cannot be predicted. Anchor: {old!r}")
    put(f"{WORKDIR}/{path}", src.replace(old, new, 1))


def build(solution, test, spec):
    """base + tests.diff [+ repair.diff] + gold.diff [+ mutant | + rename]."""
    sh("git checkout -- . && git clean -fdq", check=True)
    sh("find . -name __pycache__ -type d -prune -exec rm -rf {} + "
       "; find . -name '*.pyc' -delete")
    sh("git apply --whitespace=nowarn /tmp/tests.diff", check=True)
    if test == "repaired":
        sh("git apply --whitespace=nowarn /tmp/repair.diff", check=True)
    sh("git apply --whitespace=nowarn /tmp/gold.diff", check=True)
    if solution == "gold_renamed":
        old, new, paths = RENAME
        for path in paths:
            src = sh(f"cat '{path}'", check=True).stdout
            assert old in src, f"rename anchor missing in {path}"
            put(f"{WORKDIR}/{path}", src.replace(old, new))
    elif solution in MUTANTS:
        m = MUTANTS[solution]
        edit(TARGET, m["old"], m["new"], solution)


def graded(spec):
    from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS
    from swebench.harness.test_spec.python import get_test_directives
    meta = spec["meta"]
    cmd = MAP_REPO_VERSION_TO_SPECS[meta["repo"]][meta["version"]]["test_cmd"]
    if isinstance(cmd, list):
        cmd = cmd[-1]
    directives = get_test_directives(
        {"repo": meta["repo"], "test_patch": spec["tests_diff"]})
    full = " ".join([cmd, *directives])
    r = sh(f"export PATH={os.path.dirname(PY)}:$PATH && cd {WORKDIR} && {full}")
    log = "+ " + full + "\n" + (r.stdout or "") + "\n" + (r.stderr or "")
    return log, grade_log(log, meta)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-image", action="store_true",
                    help="leave the image resident (it is removed by default, "
                         "as the 500-task run does)")
    args = ap.parse_args()

    sys.path.insert(0, os.path.join(ROOT, "scale"))
    from run import load_instances
    instance = load_instances()[INSTANCE_ID]
    repair = open(REPAIR_DIFF, encoding="utf-8").read()
    spec = build_task_spec(instance, repair)
    check_tests_overlay(repair, spec["test_files"], INSTANCE_ID)

    subprocess.run(["docker", "rm", "-f", CONTAINER],
                   capture_output=True, text=True)
    print(f"  starting {CONTAINER} from {IMAGE} ...")
    subprocess.run(["docker", "run", "-d", "--name", CONTAINER, "-w", WORKDIR,
                    IMAGE, "sleep", "infinity"], check=True,
                   capture_output=True, text=True)
    results = {}
    try:
        put("/tmp/gold.diff", spec["gold_diff"])
        put("/tmp/tests.diff", spec["tests_diff"])
        put("/tmp/repair.diff", repair)
        for test in TESTS:
            for solution in SOLUTIONS:
                build(solution, test, spec)
                log, g = graded(spec)
                results[f"{test}/{solution}"] = {
                    "reward": g["reward"], "f2p_pass": g["f2p_pass"],
                    "f2p_fail": g["f2p_fail"], "p2p_pass": g["p2p_pass"],
                    "p2p_fail": g["p2p_fail"], "n_parsed": g["n_parsed"],
                    "f2p_failing": g["f2p_failing"],
                    "names_symbol_in_log": "UnsignedIntegerCoder" in log
                    and ("has no attribute" in log or "cannot import name" in log),
                }
    finally:
        subprocess.run(["docker", "rm", "-f", CONTAINER],
                       capture_output=True, text=True)
        if not args.keep_image:
            subprocess.run(["docker", "rmi", IMAGE], capture_output=True,
                           text=True)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, sort_keys=True)

    print(f"\n{INSTANCE_ID}  --  reward by (test variant x solution)\n")
    print(f"  {'solution':16s} {'original':>22s} {'repaired':>22s}   effect")
    for solution in SOLUTIONS:
        cells = []
        for test in TESTS:
            r = results[f"{test}/{solution}"]
            cells.append(f"{r['reward']}  F2P {r['f2p_pass']}/"
                         f"{r['f2p_pass'] + r['f2p_fail']} P2P {r['p2p_pass']}/"
                         f"{r['p2p_pass'] + r['p2p_fail']}")
        effect = MUTANTS.get(solution, {}).get("effect", "")
        print(f"  {solution:16s} {cells[0]:>22s} {cells[1]:>22s}   {effect}")

    ok = True
    c1 = results["repaired/gold_renamed"]["reward"]
    print(f"\n  C1  renamed gold, repaired test  reward = {c1}  "
          f"{'OK' if c1 == 1.0 else 'FAIL'}")
    ok &= c1 == 1.0
    print(f"      (was {results['original/gold_renamed']['reward']} on the "
          f"original test -- the witness)")

    print("\n  C2  behavioural mutants, repaired test:")
    for name in MUTANTS:
        r = results[f"repaired/{name}"]["reward"]
        o = results[f"original/{name}"]["reward"]
        caught = r == 0.0
        ok &= caught
        print(f"      {name:14s} reward = {r}  "
              f"{'CAUGHT' if caught else 'SURVIVES'}   "
              f"(original test: {o})")
        if results[f"repaired/{name}"]["names_symbol_in_log"]:
            ok = False
            print("        !! the failure names the symbol -- this mutant is "
                  "coupled, not behavioural; it proves nothing")

    g1 = results["repaired/gold"]["reward"]
    print(f"\n  G1  original gold, repaired test reward = {g1}  "
          f"{'OK' if g1 == 1.0 else 'FAIL'}")
    ok &= g1 == 1.0

    print(f"\n  -> {'PASS' if ok else 'FAIL'}    {OUT}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
