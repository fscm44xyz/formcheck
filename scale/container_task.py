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

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPRO = os.path.join(os.path.dirname(HERE), "repro")
sys.path.insert(0, REPRO)

import verifiers.v1 as vf  # noqa: E402
from formcheck_hook import FormCheckMixin  # noqa: E402
from m4_grader import grade_log  # noqa: E402

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

    async def check(self, task, runtime):
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

    async def formcheck_oracle(self, runtime):
        if self.oracle is None:
            return None, {}
        return await self.oracle.check(self, runtime), self.oracle.observes

    def formcheck_in_scope(self, anchor):
        scope = self.spec.get("in_scope")
        if scope is None:
            return True
        return anchor.get("func", anchor.get("name")) in scope
