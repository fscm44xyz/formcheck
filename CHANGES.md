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

## 10. Disk accounting: attributed, and docker's own numbers are not usable

**Closed before M2, as required. The growth was crash residue, not a per-task
leak, and the useful finding is that `docker system df` cannot be the budget.**

**What was measured.** Two controlled cycles, both timed against `df` at the
daemon's own `DockerRootDir`:

  * pull, then `docker rmi`, no container ever started -> **0 MiB residual**
  * a full task -- pull, container start, `formcheck`, teardown, `rmi` ->
    **0 MiB residual**

So nothing leaks per task. The ~5 GiB was left by the runs that were
*interrupted*: the aborted first pilot with two tasks in flight, plus killed
gate runs.

**The finding that matters.** Throughout that accumulation `docker system df`
reported `0B (0%)` reclaimable. `docker system prune` then reported reclaiming
**41.03 kB** while the filesystem gave back **5185 MiB**, after which `du -x /`
and `df` agreed to within 1 MiB. Docker's own accounting under-reported real,
on-disk, reclaimable data by three orders of magnitude. It is therefore not
usable as the disk budget for a 500-task run; `df` at `DockerRootDir` is.

**What a killed worker actually leaves.** Reproduced deliberately by killing a
task mid-flight: a 5.44 GB image, a lease naming a dead pid, and -- the part the
first version of `reconcile` missed -- a **still-running container**. A running
container holds its image, so `docker rmi` cannot remove it and
`docker image prune` will not collect its layers either. The image is
unreclaimable until the container is gone.

**Rules.**
1. *Measure the budget with `df`, never with `docker system df`.* Every byte
   figure `rotation` reports is a filesystem delta.
2. *Reconcile containers before images.* `reconcile_containers` removes
   `validate-*` containers -- the name `verifiers` itself gives them -- whose
   image no live lease holds, and it runs first, because the image sweep cannot
   succeed while one is alive.
3. *Reconcile the budget per task, and stop if it does not reconcile.* Each task
   records `disk_residual_bytes`; a residual over `RESIDUAL_ABORT_MIB` (256 MiB,
   against a measured 0) triggers a reclaim attempt, and if it survives that,
   `DiskBudgetError` stops the run. A budget that cannot be accounted for is not
   a budget.

**Verified against real residue, not a simulation.** After a deliberate mid-pull
kill, `reconcile` removed the orphaned container `validate-formcheck-0-d323189a`,
removed the 5.06 GiB image, and returned 5205 MiB by `df`, leaving zero
containers, zero images and zero leases.

`scale/rotation.py` (`reconcile_containers`, `reclaim_orphans`, `free_bytes`,
`DiskBudgetError`); `scale/run.py` (per-task residual and abort).

---

## 11. Pruning orphaned layers killed the pulls it was running alongside

**Bug, and the M2 gate is what caught it.** Entry 10's fix put
`reclaim_orphans()` -- a `docker image prune -f` -- inside `reconcile`, and
`reconcile` runs at the top of every `ImageLease` acquisition. With two workers
that means one worker prunes while another is mid-`docker pull`. `docker image
prune` drops containerd content-store leases, and an in-flight pull is *holding*
one, so the pull dies with:

    Error response from daemon: lease does not exist: not found

**How it surfaced.** M2's first attempt: all five tasks came back `unchecked` in
under three seconds each. The daemon was not broken -- a plain
`docker pull hello-world` succeeded immediately afterwards -- and the error text
contains nothing that points at the prune that caused it. Without the per-task
error being recorded in the row, this would have looked like a registry outage.

**Fail-loud is what made it harmless.** Five `unchecked` rows, five recorded
errors, zero results. The run reported that it had checked nothing, which is
exactly the distinction verifiers #2466 introduced and the reason
`writeup.md` 4.1's rule is enforced in the hook rather than in the caller.

**Rule.** *Never prune while a pull is in flight.* `_PULLS_IN_FLIGHT` counts
workers inside a pull; `reclaim_orphans` returns 0 and skips rather than running
when that count is non-zero, and pruning is now opt-in (`reconcile(..., prune=
True)`) rather than implicit. The normal path prunes exactly once, at run start,
before any worker exists. The orphan sweep is not urgent -- it exists to recover
from a *previous* run's crash -- so skipping it under contention costs nothing.

The per-pull reconcile the design requires is unchanged: stale containers and
stale images are still removed before every pull, ownership-checked against live
leases. Only the prune moved.

`scale/rotation.py` (`_PULLS_IN_FLIGHT`, `prune_is_safe`, `reclaim_orphans`,
`reconcile`); `scale/run.py`.

---

## 12. A per-task disk budget measured globally is meaningless under concurrency

**Bug, and my own abort threshold from entry 10 is what fired on it.** `run_one`
measured free space before and after each task and called the difference that
task's residual. With two workers that is not a measurement of anything.

**How it surfaced.** M2, second attempt. `pallets__flask-5014` finished cleanly
while the other worker still held the 3.57 GiB `pytest-10356` image. The global
delta charged that image to flask: **3664 MiB of "residual"** against a 256 MiB
threshold, and the run aborted on a task that had cleaned up perfectly. The
number was almost exactly one image, which is what gave it away.

**Why the guard firing is not a defence.** It stopped the run, so nothing false
was reported -- but it stopped it for a fabricated reason, and a guard that
aborts a healthy 500-task run two thirds of the way through is as expensive as
one that lets a real leak past. A check that cannot distinguish "this task
leaked" from "another task is running" is not a check.

**Rule.** *Attribute the budget to what the task owns.* The per-task check is now
structural: after the lease exits, is THIS task's image gone, and are the
containers whose ancestor is that image gone? Both are exact, cheap, and
unaffected by other workers. The run-wide free-space check is kept, but only
evaluated when no other lease is live -- at that moment free space is
attributable to the run as a whole, and a shortfall against the run's baseline
(measured after the start-of-run reclaim, so a previous run's residue is never
charged to this one) is real accumulation.

Two thresholds, two questions: "did this task clean up after itself" is answered
structurally and per task; "is this run accumulating" is answered in bytes and
only when the answer means something.

`scale/run.py` (`run_one`); `scale/rotation.py` (`image_present`,
`containers_for`).

---

## 13. `SuiteOracle` reintroduced the exact classifier bug Phase 4 had fixed

**Bug, found by M2's diff against Phase 4, and it stops M2.**

`SuiteOracle.check` decides whether a transform preserved behaviour with
`graded["p2p_fail"] == 0`. Any PASS_TO_PASS failure therefore reads as "the
transform broke the contract" and the case is classified `INVALID`.

`writeup.md` §6.2 records that Phase 4 hit this and corrected it mid-flight:

> the classifier originally called *any* P2P breakage `INVALID`. That would have
> reported this as "the transform broke behaviour". It now partitions P2P
> failures into those whose failure text names the renamed symbol (coupling) and
> those that fail any other way (genuinely invalid) [...]

M1's generic oracle was written without that partition, so it reintroduced the
bug -- in a new file, on a code path Phase 4's fix never covered.

**What it costs, measured.** `pydata/xarray-4966` is the task §6.2 was written
about, and M2 classifies it `INVALID` where Phase 4 classified it `WITNESS`. The
transformed run measures F2P 0/4, P2P 17 pass / 4 fail, reward 0.0, and every
failure carries the same text:

    E   AttributeError: module 'xarray.coding.variables' has no attribute
        'UnsignedIntegerCoder'

That is an alpha-rename, which changes no expression's value: tests failing on
that text are asserting the *name*. Under §6.2's rule every one of those
failures is coupling, and the task is a WITNESS. Under `SuiteOracle` as written,
it is a broken transform.

**Why this matters beyond one task.** `xarray-4966` is the whole evidence for
§6.2's finding that coupling does not only live in the graded test. A scale run
carrying this bug would report the P2P-coupling class as invalid transforms --
that is, it would silently convert the project's most novel result into apparent
noise, and the aggregate would show a plausible-looking `INVALID` count rather
than an obviously broken one.

**Rule, implemented.** *A failing test whose message names the renamed symbol is
coupling, not breakage.* `classify_failures` attributes every failing test
through that test's own pytest failure block -- never by scanning the log for
`E ` lines, because a passing test that runs a nested pytest session prints those
too, and the `pytest-10356` baseline log contains such a line with zero
failures. `SuiteOracle.check` now returns `not unexplained`.

`failure_sections`, `section_for` and `names_symbol` are **imported from
`repro/f4_formcheck.py`, not reimplemented.** That is the actual fix: the bug
arrived twice because the rule was written out a second time in a new file, so
the second copy has been removed rather than corrected.

**Pinned by a test, because twice is enough.** `scale/test_partition.py`, seven
cases over a recorded container log (`scale/fixtures/xarray_4966_rename.json`) --
no docker, no network, milliseconds, because a test needing a 5 GiB pull is a
test nobody runs. It pins the eight coupled failures, that `SuiteOracle.check`
itself returns preserved (not merely the helper, which is how the bug slipped in
the second time), that an unrelated failure stays INVALID, that a missing failure
section is never assumed to be coupling, and that the collapsed rule genuinely
disagrees on this fixture so the suite cannot pass vacuously. Verified by
reverting `SuiteOracle.check` to `p2p_fail == 0`: the suite fails
`test_suite_oracle_itself_returns_preserved` and exits 1.

`scale/container_task.py` (`classify_failures`, `SuiteOracle.check`);
`scale/test_partition.py`; `scale/fixtures/`; `writeup.md` §6.2.

---

## 14. §6.2's FAIL_TO_PASS figure, re-derived in-container -- and §6.2 stands

**Resolved by measurement, not by hunting for a July artifact.** No Phase 4
record for this task exists in the repo, and a July console number would not be
better evidence than a measurement inside the epoch image anyway. So the result
was re-derived deliberately and recorded as the artifact that was missing:
`scale/fixtures/xarray_4966_rename.json`, captured from a real container run.

**The harness was ruled out first**, since every defect in this file so far has
been mine (5, 8, 11, 12, 13):

  1. *Directives came from `swebench`, not a pytest default.* `pydata/xarray`
     version `0.12` -> `test_cmd` `'pytest -rA'`, `get_test_directives` ->
     `['xarray/tests/test_coding.py']`. Both from
     `MAP_REPO_VERSION_TO_SPECS` / `get_test_directives`.
  2. *The four F2P are the four §6.2 is about:*
     `test_decode_signed_from_unsigned[1,2,4,8]`.
  3. *Why they fail.* All four carry the identical message:

         E   AttributeError: module 'xarray.coding.variables' has no attribute
             'UnsignedIntegerCoder'

**So the F2P failures are coupling too**, by exactly the rule that covers the
P2P ones -- `names_symbol` returns True for all four. §6.2's finding needs **no
narrowing**: the four P2P tests asserting a name is the novel part, M2 confirms
those four exactly (17 pass, 4 fail, as §6.2 reports), and a detector inspecting
only F2P would still miss that class entirely.

**The one factual difference, recorded and not papered over.** §6.2 states all 4
F2P *pass* under this rename; in-container they fail, on the same coupling. That
changes no conclusion -- all eight failures are the same name-assertion, and the
task is a WITNESS either way -- but the sentence and the measurement disagree,
and there is no Phase 4 artifact to adjudicate which run the sentence described.
`writeup.md` is left unamended: the finding is unaffected, and the derivation now
has an artifact behind it, which is what was actually missing.

`scale/fixtures/xarray_4966_rename.json`; `writeup.md` §6.2.

---

## 15. Audit: two more places compared a count without reading the failure

**Requested after entry 13, on the grounds that comparing a number to a
threshold without asking what failed is the SHAPE of that bug and `scale/` was
likely to have more of it. It had two.**

**`witness_side` in `scale/run.py`.** It labelled a witness `p2p_involved`
whenever `p2p_fail != 0` -- a count, with no attribution. It now reads the
oracle's attributed failures, so `p2p_coupling` means "P2P tests failed AND each
one names the renamed symbol", the §6.2 class, rather than merely "P2P failed".
A third bucket, `p2p_unattributed`, exists so that a P2P failure nobody explained
can never be silently reported as the §6.2 finding.

**The control failure in `FormCheckMixin.formcheck`.** It recorded only
`scored 0.0, not 1.0`. `unchecked` is the right verdict either way, so this was
never a wrong result -- but at 50 or 500 tasks the reason is what decides the
next action, and a bare score cannot distinguish a task whose F2P never passed
from one whose P2P broke. The row now carries the F2P/P2P split and the first
failing test.

**Deliberately left alone, with the reasoning written into the code.**
`if reward == 0.0: WITNESS` in the hook reads a bare reward -- but only after the
oracle has attributed every failing test and returned INVALID if any failure did
not name the symbol. A comment now says so, because the safety of that line is a
property of the oracle above it, and changing the oracle would silently change
what it means.

`scale/run.py` (`build_record`); `repro/formcheck_hook.py` (`formcheck`);
`scale/aggregate.py` (`witness_split`).

---

## 16. Two more of the class, found by exhausting it deliberately

**The audit was widened to every comparison in `scale/` against a reward, a pass
count, a failure count or a timeout, with a one-line justification required for
each. Two could not be justified.**

**D1 -- "the oracle cannot judge" was reported as "the transform broke the
contract".** `FormCheckMixin.formcheck` tested `if satisfied is not True`, which
catches `False` (judged, broke behaviour) and `None` (could not judge) alike. The
`None` case would have been logged `INVALID` with the reason "transform broke the
contract" and **counted in the `judged` denominator** -- manufacturing evidence
out of an absence, which is the inversion `writeup.md` 4.1 exists to prevent.

Not currently reachable: `SuiteOracle` returns `None` only for SILENT operators,
which the `observes` gate routes to `UNVALIDATED` first, and `MarkerSetOracle`
never returns `None`. It is fixed anyway, because its unreachability is a
property of today's two oracles and not of the hook. `None` now yields
`UNVALIDATED` with the reason "oracle could not judge this transform" and does
not increment `judged`.

**D2 -- a failed digest collided with the control's, silently.** `_tree_digest`
ran `sha256sum <paths> 2>/dev/null || true`. Any failure -- a missing file, an
unreadable one, a path the shell mangled -- yields EMPTY output and therefore the
**same digest for every tree**. The graded memo is keyed on that digest, so the
transformed tree would have been served the control's cached grading: reward 1.0,
verdict `CLEAN`. A silent false negative, in the one direction that cannot be
noticed by reading the results -- a witness that never appears looks exactly like
a task with no witness.

Each target is now hashed individually, a missing file records a distinct
`MISSING` line rather than nothing, and the output is checked to have one line
per target or the digest raises. An all-`MISSING` result raises too: well-formed,
but identical for any other all-missing tree. `graded_report` refuses an empty
key outright.

**THIS IS THE FAILURE CLASS FORMCHECK EXISTS TO DETECT, IN FORMCHECK.** A grader
returning the wrong answer for a reason invisible in its own output is the entire
thesis of `writeup.md`. D2 is that, in the tool: the graded memo returns 1.0 for
a tree it never graded, the row says `CLEAN reward 1.0`, and the results file is
indistinguishable from a task whose reward is genuinely not form-coupled. It
biases THE NUMBER *downward*, which is the direction nobody audits, because a
missing witness looks like good news.

It was found by an audit, not by a suspicious result -- which is the argument
executed on its own code. Nothing about the outputs would have prompted anyone to
look.

**Blast radius, measured rather than asserted.** `scale/test_digest.py`
`test_collapse_makes_everything_clean` drives the real `FormCheckMixin` twice
with identical inputs, changing only whether the digest collapses:

    collapsed digest -> ['CLEAN']     working digest -> ['WITNESS']

So the consequence is not one wrong row. A collapsed digest is a property of the
IMAGE (a missing `sha256sum`), so it would hold for every task from that repo,
and the memo -- populated by the control run before any transform is applied --
serves the reference solution's 1.0 to every subsequent query. **Every judged
transform on such a task returns CLEAN and the task reports no witness.**

That signature is also what bounds the damage: a task that produced a WITNESS
proves its own digest was not collapsed. `pytest-10356` and `xarray-4966` both
did, so their `CLEAN` rows are sound. The `CLEAN` rows from tasks with no witness
-- `scikit-learn-14894`, `sphinx-9591`, `sympy-13091` (x3), `pytest-7571` -- are
the ones that cannot be cleared by that argument and are being re-verified
in-container with the corrected digest. Result recorded in `REPORT.md`.

Ongoing evidence: M3 runs the corrected digest, which RAISES on any anomaly,
across 50 tasks and 10 repos. A `sha256sum` missing anywhere in the image family
would surface as a task error rather than as silence.

**Both verified inert on the live paths before proceeding:** M0 gate IDENTICAL,
exit 0; `xarray-4966` re-run verdict-for-verdict identical (still WITNESS).

`repro/formcheck_hook.py` (`formcheck`); `scale/container_task.py`
(`_tree_digest`).

---

## 17. The M0 gate's reference could be rewritten by running the test suite

**Found by doing the thing the audit asked for -- running everything runnable in
the repo -- and watching what it touched.**

`repro/f2_gate.py` regenerates `repro/f2_verdicts.json` as a side effect of
running. That file is the July baseline the M0 gate compares the container
against. Running the gate during a routine sweep rewrote it.

**This time it was harmless**: the regenerated file was semantically identical
(`json.dumps(..., sort_keys=True)` equal, every gate-relevant field equal); the
245-line diff was line endings only, which the byte-exactness work of `86102a2`
exists to prevent and which `f2_gate`'s writer does not honour.

**The hazard is structural, not this diff.** If the operators had drifted, the
gate would compare the container against a baseline regenerated *by the same
drifted code*, and pass trivially. A gate whose reference can be rewritten by the
thing it is gating is not a gate -- it is a tautology with a table.

**Same family as D2, and worth naming as such.** Both are a check that reports
success for a reason invisible in its output: D2's memo answers a question it
never asked, and a self-regenerating baseline answers "identical?" by rewriting
what identical means. Neither would appear in any result. Both were found by
looking at the machinery rather than at the numbers.

**Rule.** *A baseline is frozen and its identity is checked, not assumed.*
`scale/fixtures/f2_verdicts.sha256` pins the reference;
`diff_verdicts.compare` verifies it before comparing anything and raises,
naming `f2_gate` as the likely cause and `git checkout` as the remedy. If the
baseline is ever meant to move, the pin is re-recorded in the same commit that
explains why.

`scale/diff_verdicts.py` (`assert_reference_unmodified`);
`scale/fixtures/f2_verdicts.sha256`; `repro/f2_gate.py`.

---

## 18. The failure attribution understood one test runner. SWE-bench has three.

**The most consequential defect in this project. It inverted M3's headline, and
it stops M3.**

`failure_sections` parsed pytest's per-test blocks (`______ test_name ______`)
and nothing else. Phase 4 ran only pytest repos, so that was sufficient and
looked complete. M3 ran ten repos and found two more shapes:

  * **pytest collection errors** -- `______ ERROR collecting path/to/test_x.py
    ______`, ONE block for a whole module that failed to import. This is exactly
    what an alpha-rename produces when a test imports the symbol by name: there
    are no per-test blocks at all.
  * **unittest / django** -- `====` then `ERROR: name (mod.Class)` then `----`
    then the traceback. No underscore rules anywhere, so the parser found
    literally nothing. Worse, a module that will not import is reported as a
    synthetic `test_cookie (unittest.loader._FailedTest)` naming the MODULE and
    never the tests that were wanted.

**Consequence.** Every failing test in those logs came back "no failure section
found", so every one landed in `unexplained`, so the oracle said the transform
broke behaviour, so the row was `INVALID`. That is coupling reported as breakage
-- the same misclassification as `CHANGES.md` 13, arriving by a different route
after 13 was fixed.

**Measured, on M3's own recorded logs.** All four `INVALID` rows name the symbol:

    astropy-12907   ImportError: cannot import name '_cstack' from
                    'astropy.modeling.separable'
    django-13195    ImportError: cannot import name 'CookieStorage'
    django-15572    AttributeError: module 'django.template.autoreload' has no
                    attribute 'get_template_directories'
    pylint-4604     AttributeError: module 'pylint.checkers.variables' has no
                    attribute 'VariablesChecker'

Re-classified with the extended attribution: **4 of 4 are WITNESS**, 48 failures
attributed, 0 unexplained.

**What it did to the headline.** M3 as run reported `W = 0` over 50 tasks, which
under `STOPPING_RULE.md` means M4 is optional and the deliverable stops being
"the number". Corrected, `W = 4`, which is the `W >= 3` branch: M4 is worth the
weekend and the number leads. **A parsing gap decided whether a weekend of
compute was worth spending**, in the direction that suppresses witnesses --
downward, again, which is the direction nobody audits.

**Rule.** *Attribution must understand every runner the corpus uses, and an
unattributable failure is a defect to investigate, not a verdict to report.* The
three shapes are handled in `f4_formcheck.failure_sections` / `section_for` --
extended in place, because `CHANGES.md` 13's lesson is that a second copy is how
this rule gets lost. Per-test blocks are preferred over module-wide collection
errors: a test with its own failure block failed on its own terms.

Pinned by six tests over the four real M3 logs
(`scale/fixtures/m3_misattributed_logs.json`), including that a per-test block
still beats a collection error.

**Not yet re-run.** M3's `scale/records/` are kept as the raw evidence. The
corrected figures are an offline re-classification of those recorded logs, and a
confirming re-run has not been performed.

`repro/f4_formcheck.py` (`failure_sections`, `section_for`);
`scale/test_partition.py`; `scale/fixtures/m3_misattributed_logs.json`.

---

## 19. The test files silently skipped tests appended after the collector

**Found immediately, while adding the tests for 18.**

Each suite ended with `TESTS = [...globals()...]` at module level, which binds
when that line executes. Six tests appended below it were never collected, and
the runner reported `7/7 passed` -- a green result that had not run the tests
written to pin the defect that had just inverted the headline.

`collect()` is now called inside `main()`, and the `if __name__` entry point sits
at the end of every file.

Same family as 17 and D2: a check that reports success without doing the work,
where the output is indistinguishable from the honest case. `53/53 across 5
suites` after the fix, against `40/40` before it -- and the 13 that were missing
are the ones that matter most.

`scale/test_*.py`.

