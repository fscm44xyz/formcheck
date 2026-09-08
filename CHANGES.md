# CHANGES — bug → rule

Every defect the scale run proves, and the rule it became. Same discipline as
`writeup.md` §9: an entry is written when a result forces a change, and it names
what would have been reported wrongly without it. A fix with no entry here did
not happen.

---

## 1. The hook was silent on zero anchors

**Bug.** `FormCheckMixin.formcheck` iterated `op.anchors(...)` and fell through
when an operator had no in-scope anchor. Nothing was logged. `f3_result.json`
therefore carried six rows where Phase 2's `f2_verdicts.json` carried seven — the
missing one being `message_reword`, `NOT_APPLICABLE`.

**How it surfaced.** Reading `f3_result.json` against `f2_verdicts.json` before
the first container run, while checking the M0 gate could be met at all. It had
not caused a wrong verdict, because the two paths were only ever compared by
their WITNESS rows.

**Why it matters at scale.** `NOT_APPLICABLE` in 7 of 12 operator-slots is the
measured coverage ceiling (`writeup.md` §6.5), and anchor availability is a
headline metric of this run. A hook that does not record N-A cannot report an
anchor-availability rate — the rate would have to be reconstructed from a
different code path than the one that produced the verdicts, which is exactly the
kind of cross-path inference that produced the false witnesses of §4.1.

**Rule.** *N-A is a verdict, not an absence.* An operator that yields no in-scope
anchor emits a `NOT_APPLICABLE` row naming the reason, distinguishing "no anchor
anywhere in the target" from "anchors exist but none inside the gold-touched
region".

`repro/f3_formcheck.py`, `FormCheckMixin.formcheck`.

---

## 2. `loud_failure` documented as the judgeability criterion, not as a flag

**Not a bug — a promotion.** `loud_failure` already gated what may be judged on a
task with no independently written contract oracle, but it read as an operator
implementation detail. It is in fact the criterion that decides what the headline
number can claim, so it is now stated as a mechanism on the base class:

- **LOUD** — an incomplete rewrite raises `AttributeError` / `ImportError` /
  `NameError` *naming the symbol* on first use, so the task's own PASS_TO_PASS
  suite is a sufficient oracle. Only a pure alpha-rename qualifies.
- **SILENT** — a reordered collection, a reworded message, a changed signature
  acceptance. No exception is raised, so a passing suite cannot be read as
  confirming equivalence, and the case is `UNVALIDATED`.

`AttributeError` is now named first because it is the one the `xarray#4966`
witness actually produced, through a P2P test reaching the symbol as a module
attribute; the previous wording listed only `NameError`/`ImportError`.

**Consequence, recorded here so it is not re-litigated later.** The headline
number over SWE-bench Verified is a `symbol_rename` number and is labelled
literally as one. The other three operators run on every task and are reported
separately by count (`UNVALIDATED` / `NOT_APPLICABLE` / `REFUSED`). Operators are
never aggregated into a single percentage.

`repro/f2_operators.py`, `Operator.loud_failure`.

---

## 3. The hook could not be imported without the July host rig

**Bug.** `FormCheckMixin` lived in `repro/f3_formcheck.py`, which imports
`run_case` at module level — and `run_case` raises `SystemExit` on import unless
a pytest checkout and an editable venv sit at fixed paths beside it. Anything
that wanted the hook therefore inherited a dependency on one machine's directory
layout, including a run inside a container where neither exists.

**How it surfaced.** The first import of the hook on the container box, before
Docker was even installed.

**Rule.** *The hook depends on the operator family and the six taskset methods,
and on nothing else.* It now lives in `repro/formcheck_hook.py`, moved verbatim;
`f3_formcheck.py` imports it from there and keeps its own pytest-specific
bindings. Behaviour is unchanged and the M0 gate compares verdicts, not file
layout.

**Bonus, recorded because `writeup.md` §9 lists them as limits.** Running the
host side on Linux rather than Windows makes two documented shims unnecessary:
`f3_fcntl_shim` (verifiers v1 does not import on Windows without `fcntl`) and the
asyncio-policy restoration that `swebench`'s import forced. Neither is loaded on
this path. `swebench_shim` is still imported and is now a no-op, since it guards
on `sys.platform == "win32"`.

`repro/formcheck_hook.py` (new), `repro/f3_formcheck.py`.

**Second instance, same bug, found by the M0 preflight.** `repro/oracle.py`
imported `run_case` at module level for `apply_alt` / `restore` / `PY`, so
importing it raised the same `SystemExit`. `scale/m0_run.py` imports it for two
strings — `REPRO` and `CONFTEST`, the reproducer and the conftest that reads
markers through the public `iter_markers()` — which depend on nothing. The
import is deferred into `run_mode`, the only function that uses those names.
Running `python repro/oracle.py` is unchanged: `main` calls `run_mode` first, so
the same `SystemExit` still fires, at the point of use rather than at import.

The rule generalises accordingly: *nothing on the container path may reach the
July host rig at import time.* Import-time coupling to a fixed local path is
invisible until the path is gone, and an env-var escape hatch would have hidden
it rather than removed it.

`repro/oracle.py`.

---

## 4. Multi-target tasks are out of scope for M0, and stay out until M1

**Not a bug — a boundary, written down now so M1 starts from a spec rather than
from a memory.**

**The condition, exactly.** The hook is single-target: `FORMCHECK_TARGET` is one
repo-relative path, `Operator.anchors(sources, target, issue)` searches that one
file for anchors, and `Operator.apply(...)` rewrites that one file. A task whose
**gold patch touches more than one file** therefore has anchors the hook cannot
see, and — worse than not seeing them — the in-scope filter is defined as "a
symbol the gold patch itself touches", so on such a task the scope set and the
searched file disagree. Anchors inside the gold-touched region of a second file
are silently dropped, and the run would report `NOT_APPLICABLE` for an operator
that in fact had an anchor.

**Why M0 does not widen the hook to fix it.** M0's whole claim is that the
container and the July rig produce the same verdicts, field for field. That claim
is only meaningful against an unmodified hook. Widening `FORMCHECK_TARGET` to a
set would change the code under test in the same commit that establishes the
baseline, and a disagreement afterwards could not be attributed. `pytest-10356`'s
gold patch touches exactly one file (`src/_pytest/mark/structures.py`), so the
boundary is not reached by the M0 task.

**What M1 must do.** Either (a) generalise `FORMCHECK_TARGET` to the set of files
the gold patch touches, with `anchors`/`apply` taking the file a given anchor
lives in, or (b) skip multi-target tasks explicitly, emitting a distinct verdict
so they are counted rather than silently under-reported. (b) is acceptable as
M1's first step provided the count is reported, and is only acceptable as a final
answer if the eligible fraction turns out to be large enough for the headline
number to mean something — a fraction M1 must measure from the gold patches
before it decides, not assume. What is not acceptable either way is the present behaviour on such a
task: a `NOT_APPLICABLE` row whose stated reason ("no anchor inside the
gold-touched region") is false.

**Until M1 lands, the selection rule is mechanical:** a task is eligible when its
gold patch modifies exactly one file. That predicate is computable from the patch
alone, before any container starts.

`repro/formcheck_hook.py` (`FORMCHECK_TARGET`), `repro/f2_operators.py`
(`Operator.anchors`, `Operator.apply`), `scale/container_task.py`
(`spec["target"]`, `formcheck_in_scope`).
