"""`Task.formcheck` -- the hook itself, independent of any one rig.

Extracted verbatim from `f3_formcheck.py`, which now imports it from here. The
move is not cosmetic: `f3_formcheck` reaches the July host rig at import time
(`run_case` raises `SystemExit` unless a pytest checkout and an editable venv
exist beside it), so anything that wanted the hook inherited a dependency on one
machine's directory layout. The hook depends on none of that -- only on the
operator family and the six methods a taskset supplies -- and a container run
needs exactly the hook.

Behaviour is unchanged. `f3_formcheck.PytestMarkMroTask` keeps its own bindings,
and the M0 gate compares verdicts, not file layout.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from verifiers.v1.runtimes import Runtime  # noqa: F401,E402  (hook signature)

from f0_equiv import Refused  # noqa: E402
from f2_operators import FAMILY, BORDER  # noqa: E402


class FormCheckMixin:
    """`Task.formcheck` by equivalence-preserving transformation.

    A taskset provides:
      FORMCHECK_TARGET    the file the reference solution changes
      formcheck_read()    -> {repo-relative path: text} for EVERY production
                             source file. Not just the target: the dynamic-reach
                             precondition of `symbol_rename` is only sound over
                             the whole production tree (an `__all__` entry in a
                             package `__init__` is invisible to a two-file scan)
      formcheck_issue()   the issue text (the contract, for the G4 precondition)
      formcheck_reset()   restore the working tree to the reference solution
      formcheck_graded()  -> (log_text, reward) for the current tree
      formcheck_oracle()  -> (satisfied: bool|None, observes: dict[str, bool])
                             None when the oracle cannot judge at all
    """

    FORMCHECK_TARGET: str = ""

    def formcheck_issue(self) -> str:
        raise NotImplementedError

    def formcheck_reset(self) -> None:
        raise NotImplementedError

    def formcheck_read(self) -> dict:
        raise NotImplementedError

    def formcheck_write(self, sources: dict) -> None:
        raise NotImplementedError

    async def formcheck_graded(self, runtime: Runtime):
        raise NotImplementedError

    async def formcheck_oracle(self, runtime: Runtime):
        raise NotImplementedError

    async def formcheck(self, runtime: Runtime) -> bool | None:
        issue = self.formcheck_issue()
        self.formcheck_log = []

        # CONTROL, before anything else. If the UNTRANSFORMED reference solution
        # does not score 1.0, then a 0.0 after a transform says nothing about
        # coupling -- it says the harness is broken. Without this guard an
        # environment fault reads as a witness, and it did: an earlier revision
        # of this file ran the graded tests in the runtime's own scratch
        # workdir, collected zero tests, scored every transform 0.0, and
        # reported four "witnesses", two of them false. Fail closed as
        # `unchecked`; never report coupling on an unproven harness.
        self.formcheck_reset()
        _, control = await self.formcheck_graded(runtime)
        if control != 1.0:
            self.formcheck_log.append(
                ("<control>", "HARNESS_UNPROVEN",
                 f"the untransformed reference solution scored {control}, not 1.0"))
            self.formcheck_reset()
            return None
        self.formcheck_log.append(
            ("<control>", "OK", "untransformed reference scores 1.0"))

        self.formcheck_reset()
        sources = self.formcheck_read()
        judged, witnesses = 0, []

        for op in FAMILY:
            if op.tier == BORDER:
                continue
            # NOT_APPLICABLE is a verdict, not an absence. An earlier revision
            # simply fell through when an operator had no in-scope anchor, so
            # the hook's log was SILENT about it -- and the silence is exactly
            # the thing the ceiling is made of: anchor availability, not
            # refusals and not oracle strength, is what bounds coverage. A run
            # that does not record N-A cannot report an anchor-availability
            # rate, so the metric would have to be reconstructed from a
            # different code path than the one that produced the verdicts.
            found = op.anchors(sources, self.FORMCHECK_TARGET, issue)
            in_scope = [a for a in found if self.formcheck_in_scope(a)]
            if not in_scope:
                self.formcheck_log.append((
                    f"{op.id}:<no anchor>", "NOT_APPLICABLE",
                    "no anchor inside the gold-touched region"
                    + (f"; {len(found)} anchor(s) elsewhere in the target"
                       if found else "")))
                continue
            for anchor in in_scope:
                label = f"{op.id}:{anchor['label']}"
                try:
                    self.formcheck_reset()
                    new, report = op.apply(self.formcheck_read(),
                                           self.FORMCHECK_TARGET, anchor, issue)
                except Refused as exc:
                    self.formcheck_log.append((label, "REFUSED", str(exc)))
                    continue
                self.formcheck_write(new)
                satisfied, observes = await self.formcheck_oracle(runtime)
                if not observes.get(report["observable"], False):
                    self.formcheck_log.append(
                        (label, "UNVALIDATED",
                         f"oracle cannot observe {report['observable']!r}"))
                    continue
                if satisfied is not True:
                    self.formcheck_log.append(
                        (label, "INVALID", "transform broke the contract"))
                    judged += 1
                    continue
                self.formcheck_reset()
                self.formcheck_write(op.apply(self.formcheck_read(),
                                              self.FORMCHECK_TARGET,
                                              anchor, issue)[0])
                _, reward = await self.formcheck_graded(runtime)
                judged += 1
                if reward == 0.0:
                    witnesses.append(label)
                    self.formcheck_log.append((label, "WITNESS", "reward 0.0"))
                else:
                    self.formcheck_log.append((label, "CLEAN", f"reward {reward}"))
        self.formcheck_reset()

        if witnesses:
            self.formcheck_witnesses = witnesses
            return False
        return True if judged else None

    def formcheck_in_scope(self, anchor) -> bool:
        return True


