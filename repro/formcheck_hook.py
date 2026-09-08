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
      FORMCHECK_TARGETS   the files the reference solution changes, in gold-patch
                          order. `FORMCHECK_TARGET` remains the single-file
                          spelling and is the tuple's only element when set
      formcheck_read()    -> {repo-relative path: text} for EVERY production
                             source file. Not just the target: the dynamic-reach
                             precondition of `symbol_rename` is only sound over
                             the whole production tree (an `__all__` entry in a
                             package `__init__` is invisible to a two-file scan)
      formcheck_issue()   the issue text (the contract, for the G4 precondition)
      formcheck_reset()   restore the working tree to the reference solution
      formcheck_graded()  -> (log_text, reward) for the current tree
      formcheck_oracle(runtime, report)
                          -> (satisfied: bool|None, observes: dict[str, bool])
                             None when the oracle cannot judge at all. `report`
                             carries `loud_failure`, which is how a task with no
                             written contract oracle decides what it may judge
    """

    FORMCHECK_TARGET: str = ""
    FORMCHECK_TARGETS: tuple = ()

    def formcheck_targets(self) -> tuple:
        """The files a transform may rewrite.

        M0 gated the container against the July rig with a hook that had ONE
        target, so the single-target path below must keep producing byte-identical
        labels and reasons -- that gate is the regression test for this widening,
        and a cosmetic difference would read as a disagreement. Hence the tuple
        collapses to exactly the old behaviour when a taskset sets only
        `FORMCHECK_TARGET`.
        """
        if self.FORMCHECK_TARGETS:
            return tuple(self.FORMCHECK_TARGETS)
        return (self.FORMCHECK_TARGET,) if self.FORMCHECK_TARGET else ()

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

    async def formcheck_oracle(self, runtime: Runtime, report: dict):
        raise NotImplementedError

    async def formcheck(self, runtime: Runtime) -> bool | None:
        issue = self.formcheck_issue()
        self.formcheck_log = []
        self.formcheck_rows = []

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
            # A bare score is not triageable. `unchecked` is the right verdict
            # either way, but at scale the reason decides what to do next: a
            # task whose F2P never passed is a different problem from one whose
            # P2P broke, and "scored 0.0" cannot tell them apart. Audited into
            # existence alongside `CHANGES.md` 13 -- comparing a number to a
            # threshold without recording what failed is the shape of that bug.
            g = getattr(self, "graded", None) or {}
            detail = ""
            if g:
                detail = (f"; F2P {g.get('f2p_pass')}/"
                          f"{(g.get('f2p_pass') or 0) + (g.get('f2p_fail') or 0)}"
                          f", P2P {g.get('p2p_pass')}/"
                          f"{(g.get('p2p_pass') or 0) + (g.get('p2p_fail') or 0)}")
                first = (g.get("f2p_failing") or []) + (g.get("p2p_failing") or [])
                if first:
                    detail += f"; first failing: {first[0]}"
            self.control_graded = g or None
            self.formcheck_log.append(
                ("<control>", "HARNESS_UNPROVEN",
                 f"the untransformed reference solution scored {control}, "
                 f"not 1.0{detail}"))
            self.formcheck_reset()
            return None
        self.formcheck_log.append(
            ("<control>", "OK", "untransformed reference scores 1.0"))

        self.formcheck_reset()
        sources = self.formcheck_read()
        self.formcheck_rows = []
        targets = self.formcheck_targets()
        multi = len(targets) > 1
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
            # Anchors are collected across EVERY gold-touched file, each tagged
            # with the file it came from, because `apply` rewrites one file and
            # must be handed the right one. Before M1 the hook searched a single
            # target while the in-scope filter asked "is this a symbol the gold
            # patch touches" -- on a multi-file task those two disagreed, and the
            # result was not merely reduced coverage but a NOT_APPLICABLE row
            # whose stated reason was false (`CHANGES.md` 4).
            found, in_scope = [], []
            for target in targets:
                for anchor in op.anchors(sources, target, issue):
                    anchor = dict(anchor, file=target)
                    found.append(anchor)
                    if self.formcheck_in_scope(anchor):
                        in_scope.append(anchor)
            if not in_scope:
                where = "the target" if not multi else (
                    f"the {len(targets)} target(s): " + ", ".join(targets))
                self.formcheck_log.append((
                    f"{op.id}:<no anchor>", "NOT_APPLICABLE",
                    "no anchor inside the gold-touched region"
                    + (f"; {len(found)} anchor(s) elsewhere in {where}"
                       if found else "")))
                self._formcheck_row(op, None, "NOT_APPLICABLE",
                                    self.formcheck_log[-1][2])
                continue
            for anchor in in_scope:
                target = anchor["file"]
                # The file enters the label only when there is more than one, so
                # a single-target task keeps the exact label M0 gated on.
                label = (f"{op.id}:{anchor['label']}" if not multi
                         else f"{op.id}:{target}:{anchor['label']}")
                try:
                    self.formcheck_reset()
                    new, report = op.apply(self.formcheck_read(),
                                           target, anchor, issue)
                except Refused as exc:
                    self.formcheck_log.append((label, "REFUSED", str(exc)))
                    self._formcheck_row(op, anchor, "REFUSED", str(exc))
                    continue
                self.formcheck_write(new)
                # The report goes to the oracle because a task with no bespoke
                # contract oracle answers "can I judge this at all?" from
                # `loud_failure`, which is a property of the transform, not of
                # the task. `MarkerSetOracle` and any other written oracle
                # ignore it.
                satisfied, observes = await self.formcheck_oracle(runtime, report)
                if not observes.get(report["observable"], False):
                    self.formcheck_log.append(
                        (label, "UNVALIDATED",
                         f"oracle cannot observe {report['observable']!r}"))
                    self._formcheck_row(op, anchor, "UNVALIDATED",
                                        self.formcheck_log[-1][2], report)
                    continue
                if satisfied is None:
                    # An oracle that CANNOT judge is not an oracle that judged
                    # and found breakage. Collapsing the two would report
                    # "transform broke the contract" on a case nobody assessed,
                    # and count it in the judged denominator -- inventing
                    # evidence out of an absence, which is the inversion 4.1
                    # exists to prevent. Not currently reachable: `SuiteOracle`
                    # returns None only for SILENT operators, which the
                    # `observes` gate above already routes to UNVALIDATED, and
                    # `MarkerSetOracle` never returns None. It is written down
                    # because the next oracle need not have either property.
                    self.formcheck_log.append(
                        (label, "UNVALIDATED",
                         "oracle could not judge this transform"))
                    self._formcheck_row(op, anchor, "UNVALIDATED",
                                        "oracle could not judge this transform",
                                        report)
                    continue
                if satisfied is not True:
                    self.formcheck_log.append(
                        (label, "INVALID", "transform broke the contract"))
                    self._formcheck_row(op, anchor, "INVALID",
                                        "transform broke the contract", report,
                                        graded_log=getattr(self, "graded_log", None))
                    judged += 1
                    continue
                self.formcheck_reset()
                self.formcheck_write(op.apply(self.formcheck_read(),
                                              target, anchor, issue)[0])
                _, reward = await self.formcheck_graded(runtime)
                judged += 1
                # Safe to read `reward` alone HERE, and only here: the oracle
                # above has already attributed every failing test, and returned
                # False (-> INVALID) if any failure did not name the symbol. So
                # a 0.0 reaching this line is a reward rejecting a transform
                # whose failures are all coupling. Change the oracle and this
                # line silently changes meaning.
                if reward == 0.0:
                    witnesses.append(label)
                    self.formcheck_log.append((label, "WITNESS", "reward 0.0"))
                    self._formcheck_row(op, anchor, "WITNESS", "reward 0.0",
                                        report,
                                        graded_log=getattr(self, "graded_log", None))
                else:
                    self.formcheck_log.append((label, "CLEAN", f"reward {reward}"))
                    self._formcheck_row(op, anchor, "CLEAN", f"reward {reward}",
                                        report)
        self.formcheck_reset()

        if witnesses:
            self.formcheck_witnesses = witnesses
            return False
        return True if judged else None

    def _formcheck_row(self, op, anchor, verdict, reason, report=None,
                       graded_log=None):
        """The structured twin of a `formcheck_log` tuple.

        `formcheck_log` stays a 3-tuple of plain strings because the M0 gate
        parses it and compares it against the July rig's table; changing its
        shape would break the one regression test this widening has. So the
        fields an aggregate needs -- which file, which tier, whether the
        operator's failure mode is loud -- are recorded here instead of being
        re-derived later from the label string. Re-deriving them from a
        different code path than the one that produced the verdict is the
        cross-path inference that manufactured the false witnesses of
        `writeup.md` 4.1.
        """
        self.formcheck_rows.append({
            "operator": op.id,
            "tier": (report or {}).get("tier", op.tier),
            "file": (anchor or {}).get("file"),
            "anchor": (anchor or {}).get("label"),
            "verdict": verdict,
            "reason": reason,
            "observable": op.observable,
            # The judgeability criterion, recorded per row so the loud/silent
            # partition and the `symbol_rename`-only scoping of THE NUMBER are
            # both computed from the row that carries the verdict.
            "loud_failure": bool(op.loud_failure),
            "graded_log": graded_log,
            # The F2P/P2P breakdown behind this row's reward, when the taskset
            # computed one. Recorded here rather than re-derived from the log
            # later: a witness is only interpretable if we can say WHICH tests
            # failed, and re-parsing the log on a different code path is the
            # cross-path inference 4.1 warns about.
            "graded_report": getattr(self, "graded", None),
            # Which failing tests were coupling and which were unexplained, from
            # the oracle that judged them (`writeup.md` 6.2).
            "failure_analysis": getattr(self, "failure_analysis", None),
        })

    def formcheck_in_scope(self, anchor) -> bool:
        return True


