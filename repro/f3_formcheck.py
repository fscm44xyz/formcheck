"""Phase 3 -- `Task.formcheck` implemented against the real verifiers v1 API.

`FormCheckMixin` supplies the hook; a taskset supplies five task-specific facts.
The hook is the mechanical half of the method: apply every applicable
equivalence-preserving transform to the reference solution, re-run the graded
tests through the runtime, and report whether the reward rejects a solution that
still satisfies the task's stated contract.

Return contract (mirrors `Task.validate`'s tri-state, per verifiers #2466):
  False  a WITNESS exists -- the reward is form-coupled.
  True   transforms were applied and judged, and none produced a witness.
  None   nothing could be judged (no anchor, or no oracle able to see what the
         applicable transforms perturb). Reported `unchecked`, never `valid`:
         absence of a check must not read as agreement.

The last case is the one that keeps this honest. A transform whose observable
class the oracle cannot watch is not evidence of anything, in either direction.
"""
import os
import sys
import shutil
import pathlib
import asyncio
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import swebench_shim  # noqa: F401,E402
import f3_fcntl_shim  # noqa: F401,E402


def _restore_proactor_policy():
    """Importing `swebench` installs `WindowsSelectorEventLoopPolicy` process-wide.
    The selector loop raises `NotImplementedError` from
    `_make_subprocess_transport`, so every `runtime.run(...)` in verifiers'
    subprocess runtime fails with an empty-message exception. Put the default
    back. Windows-only, and a collision between two libraries -- not a defect in
    either verifiers or the grader."""
    proactor = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
    if proactor is not None and not isinstance(asyncio.get_event_loop_policy(), proactor):
        asyncio.set_event_loop_policy(proactor())

import verifiers.v1 as vf  # noqa: E402
from verifiers.v1.runtimes import Runtime  # noqa: E402

import run_case  # noqa: E402
import f2_worker  # noqa: E402
import oracle as oracle_mod  # noqa: E402
from f0_equiv import Refused  # noqa: E402
from f2_operators import FAMILY, BORDER  # noqa: E402
from m4_grader import grade_log  # noqa: E402

# AFTER the import that pulls in swebench -- that is where the policy is changed.
_restore_proactor_policy()


# The hook itself lives in `formcheck_hook`, so that a rig which is not this
# one can import it without inheriting this module's dependency on the July
# host layout (`run_case` exits at import unless the checkout is beside it).
from formcheck_hook import FormCheckMixin  # noqa: E402,F401


# ---------------------------------------------------------------------------


class MarkMroData(vf.TaskData):
    pass


class PytestMarkMroTask(FormCheckMixin, vf.Task):
    """pytest-dev__pytest-10356, wired for the real `validate` CLI path.

    The reference solution, graded tests and oracle are the ones already
    committed in `repro/`; only the plumbing to `Task` is new.
    """

    FORMCHECK_TARGET = "src/_pytest/mark/structures.py"
    ORACLE_OBSERVES = {
        "callable signature (arity / parameter names)": True,
        "symbol identity (module-level name)": True,
        "order of elements in a returned collection": False,
        "human-readable text of an exception message": False,
    }
    IN_SCOPE = {"get_unpacked_marks", "normalize_mark_list", "store_mark",
                "MarkDecorator"}

    def __init__(self, data, meta):
        super().__init__(data)
        self.meta = meta

    def formcheck_issue(self):
        with open(os.path.join(HERE, "issue.txt"), encoding="utf-8") as f:
            return f.read()

    def formcheck_in_scope(self, anchor):
        return anchor.get("func", anchor.get("name")) in self.IN_SCOPE

    def formcheck_reset(self):
        run_case.restore()
        run_case.apply_patch(os.path.join(HERE, "tests.diff"))
        run_case.apply_patch(os.path.join(HERE, "gold.diff"))

    def formcheck_read(self):
        # The whole production tree under `src/` (67 files), the same scan
        # `f2_worker.read_sources` uses. An earlier revision read two files and
        # refused `MarkDecorator` on a docstring mention in the target module,
        # never seeing the `__all__` entry in `src/pytest/__init__.py` that is
        # the real reason the rename is unsafe. Same verdict, sound reason.
        out = f2_worker.read_sources()
        target = os.path.join(run_case.REPO, *self.FORMCHECK_TARGET.split("/"))
        with open(target, encoding="utf-8") as f:
            out[self.FORMCHECK_TARGET] = f.read()
        return out

    def formcheck_write(self, sources):
        for rel, text in sources.items():
            path = os.path.join(run_case.REPO, *rel.split("/"))
            with open(path, encoding="utf-8") as f:
                if f.read() == text:
                    continue  # untouched by the transform; leave the tree alone
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)

    # Change directory INSIDE the child process. Three constraints meet here:
    #   * the subprocess runtime execs in its own scratch dir
    #     (`~/.cache/verifiers/runtimes/subprocess/<name>`), where a
    #     repo-relative test path collects nothing;
    #   * an absolute test path is not a fix -- it changes the collected test
    #     ids, and the graded F2P keys are repo-relative;
    #   * and `runtime.workdir` MUST NOT be repointed at the checkout, because
    #     `SubprocessRuntime.stop()` does `shutil.rmtree(self.workdir)`. An
    #     earlier revision of this file did exactly that and deleted the pytest
    #     checkout on teardown. The runtime owns its workdir; never hand it a
    #     directory you need to keep.
    # In a real container task the workdir IS the repo, so chdir'ing in the
    # child is a faithful stand-in with none of that hazard.
    _BOOTSTRAP = (
        "import os, sys, runpy\n"
        "os.chdir(sys.argv[1])\n"
        "sys.argv = ['pytest', '-rA', '-p', 'no:cacheprovider', sys.argv[2]]\n"
        "runpy.run_module('pytest', run_name='__main__')\n"
    )

    async def formcheck_graded(self, runtime):
        workdir = getattr(runtime, "workdir", None)
        if workdir is not None and pathlib.Path(run_case.REPO) == pathlib.Path(workdir):
            raise RuntimeError(
                "refusing to run: the runtime's workdir is the checkout, and the "
                "runtime deletes its workdir on stop()")
        result = await runtime.run(
            [run_case.PY, "-c", self._BOOTSTRAP, run_case.REPO, run_case.TEST_FILE],
            env={},
        )
        log = (run_case.TEST_CMD_ECHO + "\n" + (result.stdout or "") + "\n"
               + (result.stderr or ""))
        return log, grade_log(log, self.meta)["reward"]

    async def formcheck_oracle(self, runtime):
        proj = tempfile.mkdtemp(prefix="f3_oracle_")
        try:
            with open(os.path.join(proj, "test_repro.py"), "w") as f:
                f.write(oracle_mod.REPRO)
            with open(os.path.join(proj, "conftest.py"), "w") as f:
                f.write(oracle_mod.CONFTEST)
            subprocess.run([run_case.PY, "-m", "pytest", "-p", "no:cacheprovider",
                            "-q", "--no-header", "-o", "addopts=", proj],
                           cwd=proj, capture_output=True, text=True, timeout=300)
            mpath = os.path.join(proj, "markers.txt")
            markers = set()
            if os.path.exists(mpath):
                with open(mpath) as f:
                    markers = {m for m in f.read().split(",") if m}
        finally:
            shutil.rmtree(proj, ignore_errors=True)
        return markers == {"foo", "bar"}, self.ORACLE_OBSERVES
