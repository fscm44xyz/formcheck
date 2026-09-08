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
