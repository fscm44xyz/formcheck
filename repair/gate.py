"""The two-condition repair gate, shared by every repaired task.

  C1  the RENAMED gold scores 1.0            the coupling is gone
  C2  behavioural mutants still score 0.0    the test was not hollowed out

Neither is sufficient. A test asserting nothing satisfies C1 and fails C2; the
original coupled test satisfies C2 and fails C1.

Three constraints on C2, each of which a shortcut would quietly violate:

  * the breakage must be BEHAVIOURAL with identifiers intact. A mutant that
    breaks an import fails the repaired test for the same coupled reason as
    before and re-measures the defect instead of testing the repair, so the gate
    checks that no mutant's failure names the symbol.
  * the mutants run against EVERY test variant, including the original. "The
    repair did not weaken detection" is a comparison; a mutant the original test
    also missed says nothing.
  * an edit whose anchor has drifted stops the gate. A silent no-op would
    produce a "mutant" identical to the gold that then reports itself CAUGHT.

Grading is `repro/m4_grader.grade_log`, the same offline SWE-bench-format grader
the 500-task run used, over the dataset's own F2P/P2P lists. No verdict here is
read off pytest output by eye.

Extracted from `m0b_gate.py` when the second task needed it; `m0b_gate.py` and
`m0c_gate.py` are now configs over this engine and nothing else.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (os.path.join(ROOT, "scale"), os.path.join(ROOT, "repro")):
    if p not in sys.path:
        sys.path.insert(0, p)

WORKDIR = "/testbed"


class Gate:
    """One task's gate. `cfg` is data; the procedure is here."""

    def __init__(self, instance_id, image, container, target, rename, mutants,
                 test_variants, python, out):
        self.instance_id = instance_id
        self.image = image
        self.container = container
        self.target = target          # the production file mutants edit
        self.rename = rename          # (old, new, [paths])
        self.mutants = mutants        # {name: {old, new, effect}}
        self.test_variants = test_variants   # {name: diff path or None}
        self.python = python
        self.out = out
        self.solutions = ["gold", "gold_renamed"] + list(mutants)

    # ---- container plumbing (mirrors ContainerFormcheckTask.sh / .put) ----
    def sh(self, script, check=False):
        r = subprocess.run(
            ["docker", "exec", "--workdir", WORKDIR, self.container, "sh", "-c",
             script], capture_output=True, text=True)
        if check and r.returncode != 0:
            raise RuntimeError(f"{script[:90]!r} -> {r.stderr.strip()[:300]}")
        return r

    def put(self, path, text):
        r = subprocess.run(
            ["docker", "exec", "-i", "--workdir", WORKDIR, self.container,
             "sh", "-c", f"mkdir -p $(dirname '{path}') && cat > '{path}'"],
            input=text, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"put {path}: {r.stderr.strip()[:300]}")

    def edit(self, path, old, new, what):
        """Exact single replacement, or raise -- never a silent no-op."""
        src = self.sh(f"cat '{path}'", check=True).stdout
        if src.count(old) != 1:
            raise RuntimeError(
                f"{what}: anchor appears {src.count(old)} time(s) in {path}, "
                f"expected exactly 1 -- refusing an edit whose effect cannot be "
                f"predicted. Anchor: {old!r}")
        self.put(f"{WORKDIR}/{path}", src.replace(old, new, 1))

    # ---- the matrix -------------------------------------------------------
    def build(self, solution, test):
        """base + tests.diff [+ variant.diff] + gold.diff [+ rename | + mutant]."""
        self.sh("git checkout -- . && git clean -fdq", check=True)
        self.sh("find . -name __pycache__ -type d -prune -exec rm -rf {} + "
                "; find . -name '*.pyc' -delete")
        self.sh("git apply --whitespace=nowarn /tmp/tests.diff", check=True)
        if self.test_variants[test] is not None:
            self.sh(f"git apply --whitespace=nowarn /tmp/variant_{test}.diff",
                    check=True)
        self.sh("git apply --whitespace=nowarn /tmp/gold.diff", check=True)
        if solution == "gold_renamed":
            old, new, paths = self.rename
            for path in paths:
                src = self.sh(f"cat '{path}'", check=True).stdout
                if old not in src:
                    raise RuntimeError(f"rename anchor {old!r} missing in {path}")
                self.put(f"{WORKDIR}/{path}", src.replace(old, new))
        elif solution in self.mutants:
            m = self.mutants[solution]
            self.edit(self.target, m["old"], m["new"], solution)

    def graded(self, spec):
        from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS
        from swebench.harness.test_spec.python import get_test_directives
        from m4_grader import grade_log
        meta = spec["meta"]
        cmd = MAP_REPO_VERSION_TO_SPECS[meta["repo"]][meta["version"]]["test_cmd"]
        if isinstance(cmd, list):
            cmd = cmd[-1]
        directives = get_test_directives(
            {"repo": meta["repo"], "test_patch": spec["tests_diff"]})
        full = " ".join([cmd, *directives])
        r = self.sh(f"export PATH={os.path.dirname(self.python)}:$PATH "
                    f"&& cd {WORKDIR} && {full}")
        log = "+ " + full + "\n" + (r.stdout or "") + "\n" + (r.stderr or "")
        return log, grade_log(log, meta)

    def run(self, keep_image=False):
        from container_task import build_task_spec, check_tests_overlay
        from run import load_instances

        instance = load_instances()[self.instance_id]
        diffs = {}
        for name, path in self.test_variants.items():
            diffs[name] = open(path, encoding="utf-8").read() if path else None
        primary = diffs.get("repaired")
        spec = build_task_spec(instance, primary)
        for name, text in diffs.items():
            if text:
                check_tests_overlay(text, spec["test_files"], self.instance_id)

        subprocess.run(["docker", "rm", "-f", self.container],
                       capture_output=True, text=True)
        print(f"  starting {self.container} from {self.image} ...")
        subprocess.run(["docker", "run", "-d", "--name", self.container,
                        "-w", WORKDIR, self.image, "sleep", "infinity"],
                       check=True, capture_output=True, text=True)
        results = {}
        try:
            self.put("/tmp/gold.diff", spec["gold_diff"])
            self.put("/tmp/tests.diff", spec["tests_diff"])
            for name, text in diffs.items():
                if text:
                    self.put(f"/tmp/variant_{name}.diff", text)
            for test in self.test_variants:
                for solution in self.solutions:
                    self.build(solution, test)
                    log, g = self.graded(spec)
                    old = self.rename[0]
                    results[f"{test}/{solution}"] = {
                        "reward": g["reward"], "f2p_pass": g["f2p_pass"],
                        "f2p_fail": g["f2p_fail"], "p2p_pass": g["p2p_pass"],
                        "p2p_fail": g["p2p_fail"], "n_parsed": g["n_parsed"],
                        "f2p_failing": g["f2p_failing"],
                        "p2p_failing": g["p2p_failing"],
                        "names_symbol_in_log": old in log and (
                            "has no attribute" in log
                            or "cannot import name" in log),
                    }
        finally:
            subprocess.run(["docker", "rm", "-f", self.container],
                           capture_output=True, text=True)
            if not keep_image:
                subprocess.run(["docker", "rmi", self.image],
                               capture_output=True, text=True)

        with open(self.out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, sort_keys=True)
        return self.report(results)

    # ---- reporting --------------------------------------------------------
    def report(self, results):
        variants = list(self.test_variants)
        width = max(25, max(len(v) for v in variants) + 2)
        print(f"\n{self.instance_id}  --  reward by (test variant x solution)\n")
        header = "".join(f"{v:>{width}s}" for v in variants)
        print(f"  {'solution':16s}{header}   effect")
        for solution in self.solutions:
            cells = ""
            for test in variants:
                r = results[f"{test}/{solution}"]
                cells += (f"{r['reward']}  F2P {r['f2p_pass']}/"
                          f"{r['f2p_pass'] + r['f2p_fail']} P2P {r['p2p_pass']}/"
                          f"{r['p2p_pass'] + r['p2p_fail']}").rjust(width)
            effect = self.mutants.get(solution, {}).get("effect", "")
            print(f"  {solution:16s}{cells}   {effect}")

        ok = True
        c1 = results["repaired/gold_renamed"]["reward"]
        print(f"\n  C1  renamed gold, repaired test  reward = {c1}  "
              f"{'OK' if c1 == 1.0 else 'FAIL'}")
        print(f"      (original test: "
              f"{results['original/gold_renamed']['reward']} -- the witness)")
        ok &= c1 == 1.0

        print("\n  C2  behavioural mutants, repaired test:")
        for name in self.mutants:
            r = results[f"repaired/{name}"]["reward"]
            caught = r == 0.0
            ok &= caught
            others = "  ".join(
                f"{v}: {results[f'{v}/{name}']['reward']}"
                for v in variants if v != "repaired")
            print(f"      {name:16s} reward = {r}  "
                  f"{'CAUGHT' if caught else 'SURVIVES'}   ({others})")
            for v in variants:
                if results[f"{v}/{name}"]["names_symbol_in_log"]:
                    ok = False
                    print(f"        !! {v}/{name} fails by naming the symbol "
                          "-- coupled, not behavioural; it proves nothing")

        g1 = results["repaired/gold"]["reward"]
        print(f"\n  G1  original gold, repaired test reward = {g1}  "
              f"{'OK' if g1 == 1.0 else 'FAIL'}")
        ok &= g1 == 1.0

        print(f"\n  -> {'PASS' if ok else 'FAIL'}    {self.out}")
        return 0 if ok else 1
