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

---

## 5. The gold-patch scope rule read the wrong thing out of the diff

**Bug, found by running M1's generalized path against the task M0 had already
answered.** `gold_touched_symbols` derived "the symbols the gold patch touches"
partly from the name git prints after `@@`. git prints the nearest *preceding*
definition there, which is very often a function the hunk does not modify. On
`pytest-10356` the hunk that rewrites module-level `get_unpacked_marks` carries
`def __call__(self, ...)` in its header, because `__call__` is merely the last
definition git saw before that line.

**What it produced.** Seven extra rows --
`kwonly_specialize:__call__(*, ids=...)` and six siblings -- transforms of
`MarkDecorator.__call__`'s keyword parameters, a method the gold patch never
touches. All seven happened to be `REFUSED`, so nothing false was reported. That
is luck, not a defence.

**Why it matters more than under-coverage.** `writeup.md` 3.3 restricts anchors
to what the gold patch touches so the choice of anchor cannot be made in view of
the outcome. A rule that admits untouched symbols widens the sanctioned region,
and a witness found outside it would be exactly the selection effect 3.3 exists
to prevent. The earlier docstring claimed the rule "under-approximates, which is
the safe direction". It over-approximated, and the claim was wrong.

**Rule.** *Resolve the region, do not guess it from a label.* Changed line
numbers come from the hunk arithmetic (`changed_lines`); a symbol is in scope iff
one of those lines falls inside its own `lineno .. end_lineno` range in the real
post-patch file (`symbols_covering`). Names are never read from `@@` context. A
class enters scope alongside a method it owns, because the class's range contains
the method's -- one walk, no separate rule.

`scale/container_task.py`, `changed_lines` / `symbols_covering`.

---

## 6. The mechanical scope rule is NARROWER than the set Phase 2 used by hand

**Not a bug -- a finding about the July table, recorded before it can be
mistaken for a regression.**

With the scope resolved mechanically from the patch, `pytest-10356` yields
`{get_unpacked_marks, store_mark}`. The hand-written set Phase 2 and M0 use is
`{get_unpacked_marks, store_mark, normalize_mark_list, MarkDecorator}`. The gold
patch does not touch the latter two: `normalize_mark_list` appears nowhere in
it, and `MarkDecorator` appears only as the class enclosing the `__call__` that
git names in a hunk header.

**Consequence, stated plainly.** Two of M0's seven rows --
`symbol_rename:MarkDecorator` (REFUSED) and `symbol_rename:normalize_mark_list`
(CLEAN) -- are not reachable from the gold patch alone. They exist because a
human chose a scope broader than 3.3's stated criterion. The
`symbol_rename:MarkDecorator` refusal is the row 3.2 turns on, so 3.2's worked
example rests on that human choice rather than on the mechanical rule.

**Why the rule is NOT widened to reproduce the hand-picked set.** Widening it
until it recovers rows we already know are interesting is selecting for the
outcome -- the precise thing 3.3 forbids. The mechanical rule is more faithful to
the written criterion than the hand-picked set was, and it errs toward reporting
less. So it stands, and the July table is now understood to have used a wider
scope than 3.3 describes.

**This does not weaken the M0 gate.** M0 compares the container against the July
rig over the SAME hand-picked set, on both sides. What changes is what the wider
set was ever evidence for.

`scale/container_task.py`; `repro/f2_verdicts.json` (the wider set); `writeup.md`
3.2, 3.3.

---

## 7. A module named `select.py` shadows the stdlib module asyncio runs on

**Bug, caught before it ran.** The eligibility pass was first written as
`scale/select.py`, and `scale/` goes on `sys.path` ahead of the standard library
so that `run.py` can import its siblings. `select` is a stdlib module, and it is
the one asyncio's event loop is built on. Every container in this project is
driven through asyncio.

**How it surfaced.** An import smoke-test of the M1 modules, before any run.

**Rule.** *A module that goes on `sys.path` may not take a stdlib name.* Renamed
to `scale/eligibility.py`. The failure this avoids would have appeared as an
event-loop error with no visible connection to the file that caused it.

`scale/eligibility.py` (was `scale/select.py`).

---

## 8. The graded command was hardcoded to pytest; most repos do not use pytest

**Bug.** `SweBenchFormcheckTask.formcheck_graded` ran
`python -m pytest -rA <files from the test patch>` for every task. That is right
for `pytest-dev/pytest`, which is the only repo M0 ever ran, and wrong for most
of SWE-bench Verified.

**How it surfaced.** The first M1 pilot sampled five tasks and four of them were
repos whose graded suite is not pytest: `django/django` runs
`./tests/runtests.py --settings=test_sqlite` over **dotted module paths** rather
than file paths, `sympy/sympy` runs `bin/test`, `sphinx-doc/sphinx` runs
`tox --current-env`. Only `scikit-learn` matched.

**What it would have produced.** A log the repo's parser cannot read, so
`grade_log` scores the untransformed reference below 1.0, so the control fails
and the task reports `unchecked`. Fail-loud (entry 4.1's rule) means this could
never have become a false witness -- but it would have silently emptied the
denominator, and a witness rate over the handful of pytest repos would have been
reported as a rate over Verified.

**Rule.** *Take both the command and the directives from `swebench`, never
restate them.* `MAP_REPO_VERSION_TO_SPECS[repo][version]["test_cmd"]` is the same
string `grade_log` splits the log on, and `get_test_directives` is the function
the real harness uses -- including the django transform that strips `tests/` and
turns slashes into dots. Restating either would let this drift out of agreement
with the grader silently, which is the same argument `images.py` makes for
getting image refs from `TestSpec.instance_image_key`.

`scale/container_task.py`, `SweBenchFormcheckTask.test_invocation`.

---

## 9. A blocking `docker pull` inside a coroutine serialized every worker

**Bug.** `rotation.ImageLease` was a plain `with`, and every docker call inside
it was `subprocess.run` executed directly in a worker coroutine. A ~4 GiB pull
therefore blocked the entire asyncio event loop, so `--workers 2` ran strictly
one task at a time -- and worse, it froze a task that was already mid-flight
inside its container while an unrelated worker pulled.

**How it surfaced.** Watching `progress.jsonl` during the first pilot: the second
worker's `start` landed at exactly the first worker's `pulled`, and at a moment
when both tasks were nominally in flight `docker ps` showed no running container
at all.

**Why it matters beyond speed.** The worker count is the one knob M0's resource
measurements were supposed to set. A worker count that does nothing makes the
disk-budget reasoning in `rotation.suggested_workers` untestable -- the run would
have looked well-behaved on disk for the wrong reason.

**Rule.** *No blocking docker call on the event loop.* `ImageLease` is an async
context manager and its docker calls go through `asyncio.to_thread`; reconcile is
serialized behind a lock, because two workers reconciling concurrently would each
see the other's freshly pulled image as unowned in the instant between the pull
and the lease being written. The short `docker exec` helpers in
`container_task.py` remain synchronous by the argument in its module docstring;
they are milliseconds, not minutes, and the long operations are all awaited.

`scale/rotation.py`, `ImageLease`; `scale/run.py`.

---

## 10. Disk accounting is not yet trustworthy enough for a 500-task run

**Open item, recorded because the pilot could not close it and M2 depends on it.**

After the pilot, `docker system df` reports essentially nothing resident -- one
25.9 kB `hello-world` image, no volumes, no build cache, and `scale/.leases/` is
empty, so rotation did its job. Yet the filesystem holding the image store shows
**~5 GiB more used than at the start of the session**, and that growth cannot be
attributed with the permissions available here: every directory this user can
read (`~/.cache` 0.7 GiB, `~/.venv-fc` 0.6 GiB, the two repos 29 MB) accounts for
well under a gigabyte, and `/var/lib/docker` is not readable without root.

**Why it matters.** `rotation.ensure_headroom` refuses a pull when free space is
below twice the image size, and `suggested_workers` derives the worker count from
free space. Both are only as good as the number they read. Unattributed growth of
~1 GiB per task, extrapolated over 500 tasks, is the difference between a run
that completes and one that dies of a disk error two thirds of the way through --
and by entry 9's argument it would die reporting something that looks like a
transport fault.

**What was fixed now.** The storage path is no longer hardcoded: it is read from
`docker info --format {{.DockerRootDir}}`, because where images live is the
daemon's business and a headroom check guarding the wrong filesystem passes while
the image store fills. On this WSL host the two happen to coincide, which is
exactly why hardcoding it would have gone unnoticed.

**What M2 must do before the full run.** Measure free space at the daemon's root
dir before and after a task, log the delta per task in `progress.jsonl`, and stop
the run if the per-task residual is non-zero after `docker rmi`. A budget that
cannot be reconciled per task cannot be trusted across 500 of them.

`scale/rotation.py`, `docker_root_dir` / `free_bytes` / `ensure_headroom`.

