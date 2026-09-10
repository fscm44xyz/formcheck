"""`Task.formcheck` against a SWE-bench task inside its own epoch-pinned image.

This is the same hook, the same operator family and the same classifier as
Phase 3 -- `FormCheckMixin` is imported from `repro/f3_formcheck.py`, not
reimplemented. What changes is where the work happens:

    Phase 3 (July rig)          here
    ------------------          ----
    host checkout of pytest     /testbed inside the instance image
    host venv, era-pinned       the image's own conda env
    SubprocessRuntime           DockerRuntime, image = the task's own
    fcntl + resource shims      none needed; this runs on Linux

The reproducibility finding of `writeup.md` §7 is the reason: outside the image,
2 of 4 mounted tasks could not reproduce their own reference score, and the
mandatory control then correctly switched the check off. The pins those tasks
needed are what the image already encodes.

WHICH OPERATIONS GO THROUGH THE RUNTIME, AND WHY NOT ALL OF THEM.
`FormCheckMixin`'s helper contract is synchronous for `reset` / `read` / `write`
and asynchronous for `graded` / `oracle`. The asynchronous pair is where every
verdict comes from, and both go through `runtime.run(...)` -- the real
`DockerRuntime`, exec'ing in the real container. The synchronous three are file
plumbing; they shell out to `docker exec` against `runtime.info.id`, the
container the runtime started. Making the mixin's helpers async instead would
have been the tidier shape, but it would have edited the reference
implementation that M0 gates against, which is the one thing worth avoiding
while establishing that the container and the July rig agree.
"""

import ast
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPRO = os.path.join(os.path.dirname(HERE), "repro")
sys.path.insert(0, REPRO)

import verifiers.v1 as vf  # noqa: E402
from formcheck_hook import FormCheckMixin  # noqa: E402
from m4_grader import grade_log  # noqa: E402
# The 6.2 partition itself, imported rather than reimplemented. It has now been
# lost twice by being rewritten in a new file (`CHANGES.md` 13); importing the
# reference implementation is what stops a third time.
from f4_formcheck import (  # noqa: E402
    failure_sections, names_symbol, section_for,
)

WORKDIR = "/testbed"
PATCH_DIR = "/tmp/formcheck"
# Where swebench's images put the era-pinned interpreter. Probed, not assumed:
# `python` on PATH is whatever the image's shell resolves, which for several
# repos is the system 3.x, not the environment the task was built against.
CONDA_PY = "/opt/miniconda3/envs/testbed/bin/python"

# The scan excludes test and doc trees on purpose: a transform rewrites the
# SOLUTION, never the graded tests. Same tuple as `f2_worker`, which is what the
# gate compares against.
TEST_HINTS = ("test", "tests", "testing", "doc", "docs")

_READ_TREE = r'''
import json, os, sys
root, scan = sys.argv[1], sys.argv[2]
hints = {"test", "tests", "testing", "doc", "docs"}
out = {}
for dirpath, dirs, files in os.walk(os.path.join(root, scan) if scan else root):
    rel_root = os.path.relpath(dirpath, root).replace(os.sep, "/")
    if rel_root == ".":
        rel_root = ""
    parts = [p.lower() for p in rel_root.split("/") if p]
    if any(p in hints or p.startswith(".") for p in parts):
        dirs[:] = []
        continue
    dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in hints]
    for fn in files:
        if (not fn.endswith(".py") or fn.startswith("test_")
                or fn.endswith("_test.py") or fn == "conftest.py"):
            continue
        rel = (rel_root + "/" + fn) if rel_root else fn
        try:
            with open(os.path.join(dirpath, fn), encoding="utf-8") as f:
                out[rel] = f.read()
        except Exception:
            continue
json.dump(out, sys.stdout, ensure_ascii=True)
'''


class ContainerData(vf.TaskData):
    pass


class MarkerSetOracle:
    """The `pytest-10356` contract oracle, run inside the container.

    Reads the issue's own scenario -- a test inheriting from two marked base
    classes must carry BOTH markers -- through pytest's PUBLIC `iter_markers()`,
    not through the private signature the graded test happens to assert on. It
    watches a SET of marker names, so it is blind to order and to duplication,
    and `observes` says so. That blindness is not a defect to be papered over:
    it is why `collection_reverse` comes back UNVALIDATED rather than as a
    witness.
    """

    def __init__(self, repro: str, conftest: str, expected: set):
        self.repro, self.conftest, self.expected = repro, conftest, expected

    observes = {
        "callable signature (arity / parameter names)": True,
        "symbol identity (module-level name)": True,
        "order of elements in a returned collection": False,
        "human-readable text of an exception message": False,
    }

    async def check(self, task, runtime, report=None):
        # `report` is ignored: this oracle is written against the issue's own
        # contract, so its judgeability does not depend on the transform's
        # failure mode.
        proj = f"{PATCH_DIR}/oracle"
        task.sh(f"rm -rf {proj} && mkdir -p {proj}")
        task.put(f"{proj}/test_repro.py", self.repro)
        task.put(f"{proj}/conftest.py", self.conftest)
        await runtime.run(
            ["sh", "-c",
             f"cd {proj} && {task.python} -m pytest -p no:cacheprovider -q "
             f"--no-header -o addopts= ."],
            {},
        )
        got = task.sh(f"cat {proj}/markers.txt 2>/dev/null || true").stdout.strip()
        return {m for m in got.split(",") if m} == self.expected


class ContainerFormcheckTask(FormCheckMixin, vf.Task):
    """One SWE-bench instance, checked inside its own image."""

    def __init__(self, data, spec, oracle):
        super().__init__(data)
        self.spec = spec
        self.meta = spec["meta"]
        self.oracle = oracle
        self.FORMCHECK_TARGET = spec["target"]
        self.python = CONDA_PY
        self.container = None
        self.graded_log = None

    # ---- container plumbing -------------------------------------------
    def sh(self, script, check=False):
        """A shell command in the container. Not the Runtime API -- see module
        docstring for which operations are and are not allowed to bypass it."""
        r = subprocess.run(
            ["docker", "exec", "--workdir", WORKDIR, self.container,
             "sh", "-c", script],
            capture_output=True, text=True,
        )
        if check and r.returncode != 0:
            raise RuntimeError(f"{script[:80]!r} -> {r.stderr.strip()[:300]}")
        return r

    def put(self, path, text):
        """Write a file into the container through stdin, so no host temp file
        and no quoting of the payload."""
        r = subprocess.run(
            ["docker", "exec", "-i", "--workdir", WORKDIR, self.container,
             "sh", "-c", f"mkdir -p $(dirname '{path}') && cat > '{path}'"],
            input=text, capture_output=True, text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"put {path}: {r.stderr.strip()[:300]}")

    # ---- verifiers lifecycle ------------------------------------------
    async def setup(self, runtime):
        """Runs before the hook, on the real `validate` path: `_run_check`
        provisions the runtime, calls this, and only then dispatches."""
        self.container = runtime.info.id
        probe = self.sh(f"test -x {CONDA_PY} && echo yes || echo no")
        if probe.stdout.strip() != "yes":
            found = self.sh(
                "ls -d /opt/*/envs/*/bin/python 2>/dev/null | head -1").stdout.strip()
            self.python = found or "python"
        self.sh(f"mkdir -p {PATCH_DIR}", check=True)
        self.put(f"{PATCH_DIR}/gold.diff", self.spec["gold_diff"])
        self.put(f"{PATCH_DIR}/tests.diff", self.spec["tests_diff"])

    # ---- the six hooks the mixin calls --------------------------------
    def formcheck_issue(self):
        return self.spec["issue"]

    def formcheck_reset(self):
        """Back to the reference solution: base commit + test patch + gold patch.

        `git clean -fd` is NOT enough on its own -- it skips ignored files, and
        `.pyc` is ignored, so a restored `.py` could leave a stale compiled
        module importable and the failure would surface in the NEXT case rather
        than the one that caused it (`writeup.md` §9). Bytecode is purged
        explicitly, every time.
        """
        self.sh("git checkout -- . && git clean -fdq", check=True)
        self.sh("find . -name __pycache__ -type d -prune -exec rm -rf {} + "
                "; find . -name '*.pyc' -delete")
        for name in ("tests.diff", "gold.diff"):
            r = self.sh(f"git apply --whitespace=nowarn {PATCH_DIR}/{name}")
            if r.returncode != 0:
                raise RuntimeError(f"apply {name}: {r.stderr.strip()[:300]}")

    def formcheck_read(self):
        """Every production source, not just the target.

        The dynamic-reach precondition of `symbol_rename` is only sound over the
        whole production tree: the `__all__` entry that makes renaming
        `MarkDecorator` unsafe lives in a package `__init__`, invisible to a
        narrower scan. An earlier revision read two files and refused for the
        wrong reason -- same verdict, unsound argument.
        """
        r = subprocess.run(
            ["docker", "exec", "-i", "--workdir", WORKDIR, self.container,
             self.python, "-c", _READ_TREE, WORKDIR, self.spec["scan_root"]],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"read tree: {r.stderr.strip()[:300]}")
        sources = json.loads(r.stdout)
        target = self.FORMCHECK_TARGET
        if target not in sources:
            sources[target] = self.sh(f"cat {target}", check=True).stdout
        return sources

    def formcheck_write(self, sources):
        """Only what the transform actually changed. Comparing first keeps the
        working tree honest: an unchanged file is never rewritten, so a diff of
        the container is exactly the transform."""
        current = self.formcheck_read()
        for rel, text in sources.items():
            if current.get(rel) != text:
                self.put(f"{WORKDIR}/{rel}", text)

    async def formcheck_graded(self, runtime):
        """The graded tests, through the Runtime, inside the image."""
        files = self.spec["test_files"]
        result = await runtime.run(
            [self.python, "-m", "pytest", "-rA", "-p", "no:cacheprovider", *files],
            {},
        )
        log = ("+ pytest -rA " + " ".join(files) + "\n"
               + (result.stdout or "") + "\n" + (result.stderr or ""))
        self.graded_log = log
        return log, grade_log(log, self.meta)["reward"]

    async def formcheck_oracle(self, runtime, report=None):
        if self.oracle is None:
            return None, {}
        return (await self.oracle.check(self, runtime, report),
                self.oracle.observes)

    def formcheck_in_scope(self, anchor):
        scope = self.spec.get("in_scope")
        if scope is None:
            return True
        return anchor.get("func", anchor.get("name")) in scope


# ===========================================================================
# M1: the same machinery for any SWE-bench Verified instance.
# ===========================================================================

_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_DIFF_GIT = re.compile(r"^diff --git a/(.+?) b/(.+)$", re.M)


def touched_files(patch: str) -> list:
    out = []
    for a, b in _DIFF_GIT.findall(patch):
        path = a if b == "/dev/null" else b
        if path not in out:
            out.append(path)
    return out


def changed_lines(patch: str) -> dict:
    """`{path: {line numbers on the POST-patch side the diff modifies}}`.

    WHY NOT THE NAME IN THE `@@` HEADER. git prints the nearest PRECEDING
    definition after `@@`, and that is frequently a function the hunk does not
    touch. On `pytest-10356` the hunk that rewrites module-level
    `get_unpacked_marks` carries `def __call__(self, ...)` in its header, because
    `__call__` is simply the last definition git saw before that line. Reading
    that name as "touched" admits `MarkDecorator.__call__` and its seven keyword
    parameters into the anchor set -- symbols the gold patch never modifies.

    That direction is the dangerous one. `writeup.md` 3.3 restricts anchors to
    what the gold patch touches precisely so the choice of anchor cannot be made
    in view of the outcome, and a rule admitting untouched symbols widens the
    sanctioned region and could manufacture a witness outside it. So line numbers
    are taken from the hunk arithmetic and resolved against the file's real
    structure by `symbols_covering`, which neither over- nor under-approximates.
    """
    out: dict = {}
    current, new_line = None, 0
    for line in patch.splitlines():
        m = _DIFF_GIT.match(line)
        if m:
            current = m.group(1) if m.group(2) == "/dev/null" else m.group(2)
            out.setdefault(current, set())
            continue
        if current is None:
            continue
        header = _HUNK_HEADER.match(line)
        if header:
            new_line = int(header.group(1))
            continue
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            out[current].add(new_line)
            new_line += 1
        elif line.startswith("-"):
            # A removed line has no post-patch number of its own; the edit lands
            # between the surrounding lines, so it is attributed to the current
            # position, which is inside the same definition.
            out[current].add(new_line)
        elif line.startswith(" "):
            new_line += 1
    return out


def symbols_covering(source: str, lines: set) -> set:
    """Every definition in `source` whose line range contains one of `lines`.

    A class comes back alongside its method, because a patch that edits a method
    plainly touches the class owning it -- and since the class's range contains
    the method's, that falls out of the same walk instead of needing a separate
    rule. That is how `MarkDecorator` enters scope on `pytest-10356`, which is
    the row `writeup.md` 3.2 turns on.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
            continue
        end = getattr(node, "end_lineno", None) or node.lineno
        if any(node.lineno <= n <= end for n in lines):
            names.add(node.name)
    return names


def build_task_spec(instance: dict) -> dict:
    """A `ContainerFormcheckTask` spec from one raw dataset row.

    `scan_root` is the whole repository, not a guessed source directory. The
    dynamic-reach precondition of `symbol_rename` is only sound over the entire
    production tree -- an `__all__` entry in a package `__init__` is invisible to
    a narrower scan, and an earlier revision refused `MarkDecorator` for the
    wrong reason because of exactly that (`writeup.md` 3.2).
    """
    # `eligibility`, not `select`: a module named `select` on sys.path shadows
    # the stdlib module asyncio's event loop imports.
    from eligibility import is_production_python

    gold = instance["patch"]
    targets = [f for f in touched_files(gold) if is_production_python(f)]
    return {
        "instance_id": instance["instance_id"],
        "meta": {
            "instance_id": instance["instance_id"],
            "repo": instance["repo"],
            "version": instance["version"],
            "base_commit": instance["base_commit"],
            "FAIL_TO_PASS": json.loads(instance["FAIL_TO_PASS"]),
            "PASS_TO_PASS": json.loads(instance["PASS_TO_PASS"]),
        },
        "gold_diff": gold,
        "tests_diff": instance["test_patch"],
        "issue": instance["problem_statement"],
        "target": targets[0] if targets else "",
        "targets": targets,
        "scan_root": "",
        "test_files": touched_files(instance["test_patch"]),
        # Line numbers, not names: names cannot be resolved correctly without the
        # file's structure, which only exists once the container holds the tree.
        "changed_lines": {k: sorted(v) for k, v in changed_lines(gold).items()},
    }


def classify_failures(log: str, graded: dict, name: str) -> dict:
    """Split failing tests into `renamed the symbol` and `something else`.

    F2P failures are partitioned alongside P2P ones, as `f4_formcheck` does. A
    graded test that fails with `has no attribute 'X'` after an alpha-rename is
    asserting the name exactly as a P2P test would be; which list it came from
    does not change what its failure message says.
    """
    sections = failure_sections(log)
    failing = list(graded.get("p2p_failing") or []) + \
        list(graded.get("f2p_failing") or [])
    coupled, broke, unparsed = [], [], []
    for test_id in failing:
        body = section_for(sections, test_id)
        if body is None:
            # NO FAILURE BLOCK FOUND. This is not evidence that the transform
            # broke behaviour -- it is evidence that this log has a shape the
            # parser does not know. `CHANGES.md` 18 is what happens when the two
            # are conflated: four runner formats exist, one was understood,
            # and every failure in the others was silently reported as
            # breakage. That suppressed four witnesses and inverted M3's
            # headline while every operational signal stayed green.
            #
            # So an unparsed failure makes the case UNJUDGEABLE and says so.
            # A fourth shape nobody has seen yet lands here, loudly, instead of
            # becoming an INVALID that looks like a finding.
            unparsed.append(test_id)
        elif names_symbol(body, name):
            coupled.append(test_id)
        else:
            broke.append(test_id)
    return {
        "symbol": name,
        "failing": failing,
        "coupled": coupled,
        # Attributed to a real failure block that does NOT name the symbol: the
        # transform changed behaviour. A verdict.
        "broke": broke,
        # No failure block at all: the parser did not understand this log. Not a
        # verdict -- a gap, and it must be reported as one.
        "unparsed": unparsed,
        # Kept for the records written before the split existed.
        "unexplained": broke + [f"{t} (no failure section found)"
                                for t in unparsed],
        "all_reference_the_symbol": bool(failing) and not broke and not unparsed,
        "unparsed_log_shape": bool(unparsed),
    }


class SuiteOracle:
    """The judgeability rule for a task with no independently written oracle.

    There is no bespoke contract oracle for 500 tasks, and writing 500 would be
    the whole project. What every task does have is its own PASS_TO_PASS suite --
    and `writeup.md` 4.2 is why that is not automatically enough: `pytest-10356`
    had a fix-breaking mutant (`bug_none`) that passed every P2P test, so a green
    suite does not by itself establish that a transform preserved behaviour.

    `loud_failure` is exactly the condition under which it does. If the operator's
    only realistic failure mode raises `AttributeError` / `ImportError` /
    `NameError` naming the symbol the moment the code runs, a green P2P suite
    genuinely rules that failure out, because the suite reaches the symbol. If
    the failure mode is silent -- a reordered collection, a reworded message, a
    widened signature -- the suite cannot see it and the honest verdict is
    `UNVALIDATED`, however plausible the transform's argument.

    This is what confines THE NUMBER to `symbol_rename`: it is the only operator
    in the family whose failure mode is loud.
    """

    async def check(self, task, runtime, report=None):
        """Did the transform change BEHAVIOUR, or only a name?

        A failing test has two very different causes and collapsing them is
        wrong in both directions (`writeup.md` 6.2):

          * it fails because it REFERENCES the renamed symbol -- `has no
            attribute 'X'`, `name 'X' is not defined`, `cannot import name 'X'`.
            An alpha-rename changes no expression's value, so such a test is
            asserting the symbol's NAME. That is coupling.
          * it fails any other way -- the rewrite really did change behaviour,
            and the transform is INVALID.

        The earlier version of this method asked `p2p_fail == 0` and so called
        every P2P failure broken behaviour. That is verbatim the bug Phase 4
        found and fixed, reintroduced here in a new file; it classified
        `xarray-4966` -- the whole evidence for 6.2 -- as INVALID rather than
        WITNESS. `scale/test_partition.py` pins it so there is no third time.

        Attribution is per failing test, through that test's own pytest failure
        block, never by scanning the log for `E ` lines: a passing test that
        deliberately raises prints those too, and the `pytest-10356` baseline
        log contains one with zero failures.
        """
        if not (report or {}).get("loud_failure"):
            return None
        graded = await task.graded_report(runtime)
        name = (report or {}).get("name") or (report or {}).get("anchor") or ""
        a = classify_failures(task.graded_log or "", graded, name)
        self.last_analysis = a
        if a["unparsed"]:
            # None means "cannot judge", which the hook renders UNVALIDATED --
            # never INVALID. See the note in `classify_failures`.
            return None
        return not a["broke"]

    def observes_for(self, report):
        return {report.get("observable"): bool(report.get("loud_failure"))}


class SweBenchFormcheckTask(ContainerFormcheckTask):
    """Any SWE-bench Verified instance, checked inside its own image."""

    def __init__(self, data, spec):
        super().__init__(data, spec, SuiteOracle())
        self.FORMCHECK_TARGETS = tuple(spec["targets"])
        self._graded_memo = {}
        self._scope_cache = None
        # Every digest this task computes, in order, with whether it served a
        # cached grading. This is the ONLY evidence that distinguishes a genuine
        # CLEAN from a D2 false CLEAN: both produce `reward 1.0`, so the verdict
        # cannot discriminate. A transformed tree whose digest equals the
        # control's is D2 firing, whatever the row says.
        self.digest_trace = []
        self.last_digest = None

    def _digest_paths(self):
        """Every file whose CONTENT can change what the graded run reports.

        Two groups, and the second was absent until repair-M0a:

          * `FORMCHECK_TARGETS` -- the production files a transform rewrites.
          * `spec["test_files"]` -- the graded test files, the same list
            `formcheck_graded` runs and that `test_invocation` turns into the
            runner's directives.

        The old docstring's reason for hashing only the first group -- "only the
        targets are ever modified" -- was a true statement about the detection
        family, where every transform rewrites the solution and the graded tests
        are excluded from `formcheck_read` by construction. It is false the
        moment a test-side overlay exists, because an overlay changes a test
        file and NO target. The digest would then be equal across the overlaid
        and un-overlaid trees, `graded_report` would serve the un-overlaid
        grading, and the reward would read 1.0 for a suite that never ran in the
        form being claimed.

        That is the defect shape of `REPORT.md` 7 and of D2 itself: a check
        reporting a verdict for a reason invisible in its own output. The
        widening is deliberately keyed on the same list the run actually
        executes, so the two cannot drift apart silently.
        """
        return tuple(self.FORMCHECK_TARGETS) + tuple(self.spec["test_files"])

    def _tree_digest(self):
        """Content hash of every file that can change the graded outcome.

        THIS MUST NEVER FAIL QUIETLY. The first version ran
        `sha256sum <paths> 2>/dev/null || true`, so any failure -- a missing
        file, an unreadable one, a path the shell mangled -- produced EMPTY
        output and therefore the SAME digest for every tree. The memo would then
        return the control's grading for a transformed tree: reward 1.0, verdict
        CLEAN, a silent false negative in the one direction that matters. A
        witness that never appears cannot be noticed by looking at the results.

        So each path is hashed individually and a missing file is recorded as a
        distinct `MISSING` line rather than as nothing, and the output is
        checked to have one line per path.
        """
        paths = self._digest_paths()
        script = "; ".join(
            f"if [ -f '{t}' ]; then sha256sum '{t}'; else echo 'MISSING {t}'; fi"
            for t in paths)
        out = self.sh(script)
        lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
        if len(lines) != len(paths):
            raise RuntimeError(
                f"tree digest: expected {len(paths)} line(s), got "
                f"{len(lines)} -- refusing to return a digest that could "
                f"collide with another tree's. stderr: "
                f"{out.stderr.strip()[:200]}")
        if all(ln.startswith("MISSING ") for ln in lines):
            # Well-formed but degenerate: every path absent means the tree is
            # not in a state where grading it says anything, AND the digest
            # would be identical for any other such tree. Raise rather than
            # return a value that is technically distinct but semantically
            # empty.
            raise RuntimeError(
                f"tree digest: every digested path is missing "
                f"({', '.join(paths)}) -- refusing a degenerate digest")
        return hashlib.sha256("\n".join(lines).encode()).hexdigest()

    def test_invocation(self):
        """The command SWE-bench itself would run for this task, plus its own
        test directives.

        Hardcoding `pytest` was wrong and the pilot proved it: of five sampled
        tasks, four are repos whose graded suite is not pytest at all -- django
        runs `./tests/runtests.py` over DOTTED MODULE paths, sympy runs
        `bin/test`, sphinx runs `tox`. A pytest invocation on those produces a
        log that `grade_log` cannot parse, the control cannot reach 1.0, and the
        task is reported `unchecked`. Fail-loud kept that from becoming a false
        witness, but it would have silently emptied the denominator.

        Both halves come from `swebench` rather than from a rule restated here:
        `MAP_REPO_VERSION_TO_SPECS[repo][version]["test_cmd"]` is the same string
        `grade_log` splits the log on, and `get_test_directives` is the same
        function the real harness uses -- including the django transform that
        strips `tests/` and turns slashes into dots. Restating either would let
        this drift out of agreement with the grader silently.
        """
        from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS
        from swebench.harness.test_spec.python import get_test_directives

        meta = self.meta
        cmd = MAP_REPO_VERSION_TO_SPECS[meta["repo"]][meta["version"]]["test_cmd"]
        if isinstance(cmd, list):
            cmd = cmd[-1]
        directives = get_test_directives(
            {"repo": meta["repo"], "test_patch": self.spec["tests_diff"]})
        return cmd, directives

    async def graded_report(self, runtime):
        """The full grading dict for the current tree, computed at most once.

        The hook asks the oracle whether the transform preserved behaviour and
        then, separately, re-applies the same transform and runs the graded
        tests. Here both questions are answered by one pytest run over a tree
        that is byte-identical across them, so the result is memoized on the
        content hash. Keying on content rather than on a call counter is what
        makes the reuse safe.
        """
        key = self._tree_digest()
        if not key:
            raise RuntimeError("tree digest empty -- refusing to key the "
                               "graded memo on it (see CHANGES.md D2)")
        hit = key in self._graded_memo
        self.last_digest = key
        self.digest_trace.append({"digest": key, "memo_hit": hit})
        if not hit:
            cmd, directives = self.test_invocation()
            full = " ".join([cmd, *directives])
            # The env's bin directory goes on PATH rather than activating conda:
            # `bin/test`, `runtests.py` and `tox` each resolve their own
            # interpreter, and prepending the path the probe in `setup` already
            # found gets all three without depending on a login shell.
            bindir = os.path.dirname(self.python)
            result = await runtime.run(
                ["/bin/bash", "-c",
                 f"export PATH={bindir}:$PATH && cd {WORKDIR} && {full}"], {},
            )
            # The echoed line must contain `cmd` verbatim: `grade_log` splits the
            # log on exactly that string to find where the run begins.
            log = ("+ " + full + "\n"
                   + (result.stdout or "") + "\n" + (result.stderr or ""))
            self._graded_memo = {key: (log, grade_log(log, self.meta))}
        # Kept current here rather than only in `formcheck_graded`: the oracle
        # grades the transformed tree through this method, and a row that
        # records `self.graded` set elsewhere would attach the CONTROL's report
        # to a verdict about a transform.
        self.graded_log, self.graded = self._graded_memo[key]
        return self._graded_memo[key][1]

    async def formcheck_graded(self, runtime):
        graded = await self.graded_report(runtime)
        return self.graded_log, graded["reward"]

    async def formcheck_oracle(self, runtime, report=None):
        satisfied = await self.oracle.check(self, runtime, report)
        # Kept on the task so the row records WHICH tests were judged coupling
        # and which unexplained. A verdict of INVALID that cannot name the test
        # that justified it is not checkable.
        self.failure_analysis = getattr(self.oracle, "last_analysis", None)
        return satisfied, self.oracle.observes_for(report or {})

    def _scope(self):
        """The symbols the gold patch touches, resolved against the real files.

        Computed once, after `formcheck_reset` has put the reference solution in
        the tree, because the post-patch line numbers in `changed_lines` only
        mean anything against the post-patch file.
        """
        if self._scope_cache is None:
            scope = set()
            for path in self.FORMCHECK_TARGETS:
                lines = set(self.spec["changed_lines"].get(path, ()))
                if not lines:
                    continue
                scope |= symbols_covering(self.sh(f"cat '{path}'").stdout, lines)
            self._scope_cache = scope
        return self._scope_cache

    def formcheck_in_scope(self, anchor):
        scope = self._scope()
        if not scope:
            return False
        return anchor.get("func", anchor.get("name")) in scope
