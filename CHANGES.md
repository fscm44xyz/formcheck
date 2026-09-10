# CHANGES — bug → rule

Every defect the scale run proves, and the rule it became. Same discipline as
`writeup.md` §9: an entry is written when a result forces a change, and it names
what would have been reported wrongly without it. A fix with no entry here did
not happen.

---

> ## ⚠ Before you rewrite this history
>
> **Seven commits in this repository are cited as evidence, and the citations are
> load-bearing.** `REPORT.md` §1 and §2 argue that the stopping-rule threshold and
> the sensitivity axis were fixed *before* the results they judge, and the proof of
> that is commit ordering. They are tagged:
>
> ```
> git tag -n99 -l 'evidence/*'
> ```
>
> A rebase, amend, squash or `filter-branch` touching any of them breaks that
> proof. **It has already happened once** — a rewrite killed six citations at
> once and nothing reported it, because a dead hash reads exactly like a live one
> (entry 25). If you must rewrite, move the tags afterwards and re-run:
>
> ```bash
> git merge-base --is-ancestor evidence/stopping-rule evidence/ids-frozen \
>   && git merge-base --is-ancestor evidence/ids-frozen evidence/m3-results \
>   && git merge-base --is-ancestor evidence/tier-axis evidence/m1-pilot \
>   && echo "ordering holds"
> ```
>
> Publishing anything that cites them without that command passing is the defect
> this file exists to record.

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

## 18. The failure attribution understood one test runner. SWE-bench has four.

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
shapes are handled in `f4_formcheck.failure_sections` / `section_for` --
extended in place, because `CHANGES.md` 13's lesson is that a second copy is how
this rule gets lost. Per-test blocks are preferred over module-wide collection
errors: a test with its own failure block failed on its own terms.

**The count in this entry's title was three when it was written, and is four.**
Three shapes were known at M3. The fourth -- sympy's `bin/test`, whose blocks are
underscore-delimited and so parse, but which labels them
`path/to/test_x.py:test_name` while swebench reports the bare name -- was found
afterwards by the closure this entry installed rather than by a wrong number,
which is the closure working as designed. Four is also the number of distinct
runners in the corpus: django's `runtests.py` (231 tasks), pytest (150), sympy's
`bin/test` (75) and sphinx's `tox` (44), counted from
`MAP_REPO_VERSION_TO_SPECS` over all 500. `scale/test_partition.py` pins all
four.

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

---

## 20. `live_refs` raced another worker's `release` and killed the task

**Found by M4's own monitor, 0.8s into `astropy-8707`, at four workers.**

`Leases.live_refs()` iterates `os.listdir(self.dir)` and opens each lease. That
listing is a SNAPSHOT: another worker can release its lease between the listdir
and the open. The `except (OSError, ValueError)` did catch the failed open --
but then called `os.remove(path)` inside the handler, and that raised
`FileNotFoundError` again, unhandled, out of `reconcile`, out of `ImageLease`,
and the task died before its container ever started.

The give-away in the record is that the missing file names a **different task**:

    astropy__astropy-8707 failed with
    FileNotFoundError: .../scale/.leases/..._astropy-7166_latest

**Not the silent class.** It crashes loudly, the task is recorded `unchecked`
with `mountable: false` and the exception in `error`, and no result is
fabricated. It costs coverage, not correctness -- but at four workers over 500
tasks it costs it repeatedly.

**Rule.** *Every removal in the lease directory races every other worker, so
"already gone" is the SUCCESS case.* `_unlink` swallows `FileNotFoundError` and
is used on both removal paths. Two tests pin it: a lease vanishing mid-scan, and
`release` being idempotent.

**Resume semantics, fixed alongside.** `build_record` set `completed: True`
unconditionally, so `--resume` would have SKIPPED a task that crashed -- silently
dropping it from the denominator, which is the silent class. `completed` is now
`error is None`. A control FAILURE stays complete, because "the task could not be
checked" is a legitimate result; only "the harness broke" is retried.

M4 is running with the pre-fix module loaded, so the race can still cost it
tasks. Those are identifiable (`error` is non-null) and will be re-run with the
fixed code into the same records directory rather than restarting a 7-hour run.

`scale/rotation.py` (`_unlink`, `Leases.live_refs`); `scale/run.py`
(`build_record`).

---

## 21. 330 tasks burned in sequence and nothing stopped the run

**Instance six of the family, and the worst-behaved of them: the monitor
reported healthy the entire time, because it was watching for causes it already
knew.**

M4 exhausted Docker Hub's anonymous pull quota. Every subsequent `docker pull`
returned `429 Too Many Requests` in about two seconds, so each "task" completed
in 2.5s having pulled nothing, started nothing and judged nothing. In 32 minutes
the run consumed **380 of its 500 tasks and produced 334 errors.**

**Why nothing caught it.** The monitor filtered on `DiskBudgetError`,
`Traceback`, `abort` and `UNCHECKED` — every failure mode that had already bitten
this project. A fast, clean, *recorded* failure is none of those. The per-task
disk budget was satisfied (nothing was pulled, so nothing leaked). The control
check was satisfied vacuously (it never ran). Every guard reported success
because every guard was answering a question about a cause that had already been
seen.

It was found because a human asked whether the run was still going, and the
**rate** was impossible: 362 of 500 in 32 minutes against a 6.4-hour projection.
Nothing in the machinery said so.

**Two facts about the quota, both wrong in the first diagnosis.** It is 100 pulls
per **hour**, not per six hours; and `~/.docker/config.json` did not exist, so
every pull in this project has been anonymous. Both were checked rather than
assumed once the first assumption proved wrong.

**Rule 1 — assert something causally necessary, not the absence of known
causes.** A real task must pull an image, start a container and run the control
suite. It cannot be fast. `MIN_PLAUSIBLE_TASK_SECONDS = 25` with
`BURN_STREAK = 8`: eight consecutive tasks under the floor aborts the run. The
threshold is measured, not guessed — across 97 tasks whose control passed the
fastest was **30.5s**; across 357 tasks burned by the limit the slowest was
**19.6s** and the 95th percentile **3.4s**. The two populations do not overlap
and 25 sits in the empty gap between them.

**Rule 2 — pace off the registry's own headers, never a constant.**
`x-ratelimit-limit` and `x-ratelimit-remaining` are published on every request.
`wait_for_pull_slot` reads them, holds `PULL_RESERVE = 8` in hand, and derives
its wait from `window / limit` rather than a literal. `remaining` is logged with
every pull, so the margin is visible in `progress.jsonl` instead of reconstructed
after a burn. An unmeasurable quota logs `rate_limit_unknown` and proceeds —
"cannot measure" is not "fine".

**Rule 3 — an infrastructure refusal is not a task result.** A 429 leaves the
task *unattempted*: `RateLimited` is a distinct exception, `run_one` writes **no
record at all**, and the task returns to the queue for a resume. Recording it as
a failed task is what let 334 refusals look like 334 results, and it is the same
error as reporting an unparseable log as `INVALID` (`CHANGES.md` 18).

**Fixing the ceiling would not have fixed the defect.** Authenticating raises the
quota to 200/hour and would have hidden this for another run. A harness that
survives only because it has headroom is not fixed.

`scale/rotation.py` (`hub_rate_limit`, `wait_for_pull_slot`, `is_rate_limited`,
`RateLimited`); `scale/run.py` (`MIN_PLAUSIBLE_TASK_SECONDS`, `BURN_STREAK`,
`BurnDetected`); `scale/test_burn.py`.

---

## 22. Authenticating removed a ceiling and added a failure mode; the retry loop then prolonged its own block

**The episode, in order, because no part of it was predictable from the quota
arithmetic.**

The anonymous quota (100 pulls/hour) was measured, paced against, and working:
the governor logged 76 waits and the run was progressing at 33s/task. To buy
headroom the operator authenticated — and rotated the token twice. Docker Hub
responded by blocking **login attempts** for the IP. Every subsequent pull then
failed, not on the pull quota but on `POST https://auth.docker.io/token`:

    429 Too Many Requests
    failed to authorize: failed to fetch oauth token

**Two lessons, neither derivable from the numbers.**

*Authentication is not a strictly larger allowance.* It raised the pull ceiling
from 100 to 200/hour and simultaneously introduced a failure mode anonymous
operation does not have — a login-attempt block, which no amount of pull-pacing
can avoid or clear. "More quota" was the wrong model. The remedy was
`docker logout`: the anonymous path that had been working all along.

*A tight retry loop against a rate-limited registry prolongs its own block.*
Four workers cycled the queue at 2.6 tasks/second, each attempt hitting the same
blocked endpoint. The run was not waiting out the block; it was continuously
re-triggering it.

**And a defect of mine underneath both.** `wait_for_pull_slot` probed
`ratelimitpreview/test` and read `remaining: 100` while every real pull was
refused. That probe measures the pull quota; the block was on token issuance.
**A measurement that looks right and means nothing** — instance seven of the
family, in the code written to prevent instance six. It was worse than no
governor, because it reported healthy throughout.

**Rules.**

1. *A refusal storm must quiet the run down, not speed it up.* Three consecutive
   refusals (one can be a worker race, two its tail, three is systematic) trigger
   a backoff doubling from 60s — the least that can free a slot at 100/hour — to
   a 900s cap. Every refusing worker waits, so the run goes quiet.
2. *The liveness invariant counts refusals.* See entry 23; this is the part that
   actually failed.
3. *A validity marker needs an end.* `progress.jsonl` carries a
   `quota_readings_suspect` record with `from_t` AND `to_t`, closed when the
   operator logged out and anonymous access was verified by a real layer pull. A
   marker that outlives its condition makes a correct field look wrong, which is
   the same defect family as a field that looks right and is wrong.

`scale/rotation.py` (`note_refusal`, `note_pull_success`, `REFUSAL_STREAK`,
`BACKOFF_*`); `scale/progress.jsonl` (`quota_readings_suspect`).

---

## 23. Two correct guards cancelled at the seam, and nothing reported it

**The strongest instance of the family, and the only one found by noticing the
ABSENCE of an event.**

Entry 21 produced two requirements from one incident. Both were right:

  * *separate an infrastructure refusal from a task result* — a 429 must leave
    the task unattempted, not failed;
  * *assert something causally necessary* — a real task cannot be fast, so a
    streak of impossibly fast outcomes aborts the run.

Both were implemented. Both were individually correct. The first was implemented
as `return None` before a record is written — and that return sat **before** the
line feeding the second. The refusal path skipped the liveness check entirely.

So when the registry blocked us, **107 tasks were cycled in 41 seconds and the
detector never looked.** The run was stopped by hand.

**Why this one is worse than the other seven.**

  * *Correctness of parts does not compose.* No review of either requirement
    alone would have found this. Each is right. The defect lives only in their
    interaction, at a seam neither owns.
  * *A safety mechanism was silently disabled by another safety mechanism*, and
    the system reported nothing — no warning, no degraded mode, no event.
  * *It was found by an operator noticing that an event was missing*, not by any
    check. Nothing in the machinery is capable of observing its own silence.

**And it was nearly recorded backwards.** Reading a dead process and a frozen
log, the conclusion drawn was that the invariant had worked — that it had fired
on a cause it was not written for. It had not. `progress.jsonl` contains zero
`burn pattern` events and the log contains no `BurnDetected`; the run ends
mid-queue at task 174 because a human killed the process. Accepting that credit
would have written a guard's success into the permanent record as evidence FOR
the design, on the basis of a clean-looking outcome nobody asked the cause of --
which is precisely the failure this project exists to detect, committed about
this project's own safety mechanism.

**What did hold**, and is worth keeping separate from what did not: none of
those 107 refusals wrote a record, fabricated a row, or produced an `INVALID`
from an infrastructure cause. Every refused task was verified still absent from
`records_m4/` and back in the queue. Entry 21's rule 3 worked exactly as
designed. Rule 1 was disabled by it.

**Rule.** *The invariant is "the run must be progressing", not "tasks must be
slow".* A refusal is zero seconds of work and enters the streak like any other
non-progress outcome; eight consecutive non-progress results, in any mix, abort.

**The general rule this forces, which is the part that outlives the incident.**

> A guard that has never fired in production is indistinguishable from a guard
> that CANNOT fire.

Both look identical from the outside: silence. The partition already had this
property by accident — reverting `SuiteOracle.check` makes the suite fail, so it
is proven capable of firing. Nothing else did. `scale/test_guards_fire.py` now
proves, for every guard, that it fires: the burn detector on fast completions
AND on a refusal storm, that it emits its abort event when it does, the cleanup
guard on a leaked image and on a leaked container, the frozen-baseline pin on a
modified reference, the headroom guard, the merged-rate guard, the digest guard.

Guards were also **extracted into callable functions** (`check_progress`,
`check_task_cleanup`) to make that possible: an invariant inlined in a loop
cannot be driven to its raise by a test, and one that cannot be tested cannot be
proven capable of firing. A test that only checks the predicate — `all(t <
floor)` — proves arithmetic, not that anything happens.

`scale/run.py` (`check_progress`, `check_task_cleanup`, `guarded`);
`scale/test_guards_fire.py`.

---

## 24. The run-wide disk guard fired for the first time, and it was wrong

**The ninth instance of the family, and the first found by a guard reporting
something rather than nothing.**

M4's final task, `sympy__sympy-24661`, completed valid — control true, no leaked
containers, `leaked_image` false, zero witnesses — and the run aborted on the
line after it:

```json
{"event":"abort","instance_id":"sympy__sympy-24661",
 "reason":"run-wide disk did not return to baseline","residual_mib":325.0}
```

The arithmetic was exact. `baseline_free` was `1021130674176`; free space at the
check was `1020789870592`; the difference is `340803584` bytes, 325.0 MiB, over a
256 MiB threshold. Nothing was mis-subtracted. The defect is one level up: **the
quantity it computed was not a property of the run.**

`free_bytes()` is `shutil.disk_usage(docker_root_dir()).free` — statvfs on the
filesystem holding the docker root. On this host that is `/`, which also holds
`$HOME` and the repo. Every writer on the machine is charged to the run.

**What actually consumed it.** `~/.npm/_cacache` gained 100.2 MiB inside the run
window, 97,003,648 of those bytes in a single blob written at 22:44:44. Its own
log names the writer:

```
verbose title npm view @anthropic-ai/claude-code@latest version
```

An editor's update check, re-caching a registry document, on a filesystem the
harness happens to share. The free-space high-water mark returned to within
**1.5 MiB** of baseline at 18:35 and to 5.7 MiB at 20:17; from 22:44 onward it
never came back below 318.9 MiB and stayed flat there for three hours. A step,
not accumulation.

**Docker was clean, and the per-task guard proved it.** Across 393 logged tasks:
`1,956,741,070,109` bytes pulled and `1,956,741,070,109` removed — **a difference
of zero**, every pulled image accounted for, no image pulled and not removed,
`leaked_image` false and `leaked_containers` empty on every task, `reclaim_orphans`
returning 0 every time. The structural per-task check — *is MY image gone, are MY
containers gone* — was right 500 times and reconciles to the byte. It is the
guard that works.

**Two defects, and a threshold change fixes neither.**

1. *It measures the wrong quantity.* Whole-filesystem free space cannot separate
   this run's bytes from a co-tenant's. It also charges the run for its own
   output: `records_m4/` plus `progress.jsonl` are ~4 MB the run must write and
   can never give back, so the guarded quantity cannot reach zero by
   construction. Raising the threshold buys silence, not correctness — and the
   next false positive is whatever writes more than the new number.
2. *It is structurally tail-only.* The check was gated on `not leases.live_refs()`,
   and a lease is held from the start of a pull. Under four workers that
   condition is essentially only true when the run drains. Free space was below
   threshold at every quiet moment from 22:44 onward and no abort fired, because
   another worker always held a lease. A guard written to catch mid-run
   accumulation could only ever fire on the last task — which is why the audit
   found it had never fired, and why, when it finally did, it fired on three
   hours of unrelated drift with the last task's name attached to it.

**The fix: ask the run-wide question the way the per-task one is already asked.**
`rotation.unowned_footprint(leases)` returns the images and containers belonging
to this harness that no live lease accounts for — `docker images` filtered by
`NAMESPACE`, `docker ps` filtered by `CONTAINER_PREFIX`. `run.check_run_footprint`
raises on a non-empty answer. The three things that made the old version wrong
cannot affect it: a co-tenant is in neither namespace; the run's own records are
neither images nor containers; and a worker still holding an image is holding a
lease, so its image is *owned* rather than residue — which means the check is
evaluable at any moment instead of only once the run has drained.

`CHANGES.md` 10 still stands and is not reopened: docker's own space accounting
is still not usable as a budget, orphaned layer data is still collected by
`reclaim_orphans` and still measured with a `df` delta. What changed is only what
may **abort** a run. Free space is still recorded on every task as
`disk_residual_bytes`; it is now an observation, not a budget, and the record
schema is unchanged so M4's 500 records stay comparable.

**Guards tests.** Five added to `scale/test_guards_fire.py`: it fires on an
unowned image, fires on an unowned container, emits its abort event when it
fires — and, the two that are the actual point, **stays silent** while another
worker's lease holds an image, and **stays silent when `free_bytes()` returns
zero**. That last one is the regression test for this entry: free space is now
irrelevant to the decision, so collapsing it entirely must change nothing.

**Where this sits in the family.** The other eight are checks that reported
success for a reason invisible in their own output. This one reported *failure*
for a reason invisible in its own output, which is the same defect with the sign
flipped and is worth naming separately, because the operational consequence
differs: a false green is believed, and a false red is retuned. The temptation
here was to move 256 to 512 and move on. That would have preserved both defects
and bought a quieter run.

It also cost nothing and could have cost the run. `write_record` completes before
the raise, so `sympy-24661`'s record is intact and all 500 are present; the
abort landed on the last task of the queue. Fired eighty tasks earlier — which
the arithmetic permitted from 22:44 onward, and only the lease gate prevented —
it would have killed a run that was working perfectly.

`scale/rotation.py` (`unowned_footprint`, `_validate_containers`;
`RESIDUAL_ABORT_MIB` removed); `scale/run.py` (`check_run_footprint`, `run_one`);
`scale/test_guards_fire.py`.

---

## 25. Six citations that looked verifiable and were not

**The tenth instance of the family, and the first where the unverifiable thing
was the evidence for a claim rather than the claim itself.**

`REPORT.md` §1 asks the reader to check that the stopping rule was fixed before
the data:

> *"it was committed in `0d6e786` at 14:39 on 2026-09-08, before M3's ids were
> frozen in `664a3ab` at 16:25 and before M3's results existed in `18d22b5` at
> 18:24."*

That paragraph exists for exactly one purpose: to let a sceptic confirm the
threshold was not chosen to fit the answer. **All three hashes were dead.** The
repository's history had been rewritten, every commit from the M4 series onward
got a new hash, and six citations across three files silently stopped resolving:

The six hashes in the left column below **are dead, deliberately, and stay that
way**: they are the historical record of what the documents used to cite, not
live references. `git show 0d6e786` failing is the point of the entry. Any
automated check over citations in this repository must exempt this table.

| dead hash, as it was cited | where it was cited | durable handle now |
|---|---|---|
| `0d6e786` | REPORT.md §1 ×2 | `evidence/stopping-rule` (`78c547b`) |
| `664a3ab` | REPORT.md §1 | `evidence/ids-frozen` (`fb930c8`) |
| `18d22b5` | REPORT.md §1 | `evidence/m3-results` (`294ef59`) |
| `79694c9` | REPORT.md §2, `records_m1_pilot/README.md` | `evidence/m1-pilot` (`e8f3c0c`) |
| `a1bbbfa` | REPORT.md Appendix A | `evidence/m4-run` (`38a26e2`) |
| `65ba7e1` | writeup.md §5, §9.3 | `evidence/m0-gate` (`4ab9760`) |

The right column has itself been rewritten once since: a third history rewrite,
to strip commit-message trailers, moved every one of those commits again. The
tags absorbed it — that is what they are for — and the hashes shown are the
values after it.

**The shape is the family's.** A citation renders as a plausible hash whether or
not it resolves; nothing about reading the document reveals that
`git show 0d6e786` fails. The check that would have caught it — running the
verification instruction the report itself prints — was never executed after the
history changed. That is the same mechanism as **#18** (a parser that produced a
plausible verdict for logs it could not read) and **D2/#16** (a memo that served
a grading it had not performed): *evidence carried forward without re-executing
the check that would have caught it.*

**One of the six was introduced while fixing something else.** Writing §9.3's
retraction (entry 24's sibling fix), `65ba7e1` was copied out of §5 into the new
paragraph. It was **already dead at the moment it was written**, and it was
copied rather than checked. A citation was propagated on the authority of another
citation, which is precisely the failure this file keeps recording.

**And the investigation that found all this made the same mistake in miniature.**
Asked whether a push had landed, the check run was `git rev-parse` against one
ref — `origin/m0-in-container` — and the conclusion reported was that *the
changes were not on the remote*. They were: they had gone to `origin/main`, which
was never looked at. The check was real and its result was accurate; **the claim
was wider than the check**. That is the family's shape with the object swapped:
not a check reporting success it did not earn, but a true observation about one
ref restated as a conclusion about all of them. A verification is only as broad
as the thing it enumerated, and "the remote" is not one ref.

**Why hashes were the wrong handle, and tags are the fix.** These commits are not
referenced for their content; they are referenced for their *position in time* —
the report's argument is that one thing was committed before another. A proof of
ordering must not depend on nobody rewriting history, and a bare hash does.
Seven annotated tags now carry that role, each stating what the commit **proves**
rather than what it contains:

```
evidence/tier-axis       the HIGH/MEDIUM axis, fixed before any witness was known
evidence/m0-gate         the container reproduces the July rig, field for field
evidence/m1-pilot        the earliest task records in the repository
evidence/stopping-rule   the W>=3 threshold, fixed before the sample was drawn
evidence/ids-frozen      M3's 50 ids, frozen before any container started
evidence/m3-results      the first commit at which W=4 exists
evidence/m4-run          the 500 records and summary.json the report aggregates
```

Citations now read as tag plus today's hash, so a reader has both a durable
handle and a value they can paste. `REPORT.md` §1 states that the tags are the
durable handle and prints a `git merge-base --is-ancestor` chain that verifies
the ordering directly; that command was executed before this entry was written,
and it passes.

**These seven commits are cited as evidence and must not be rewritten.** Any
rebase, amend, squash or `filter-branch` that touches them invalidates the
ordering proof in `REPORT.md` §1 and §2. If one must be rewritten, move its tag
and re-run the two `merge-base` checks before publishing anything that cites it.

`REPORT.md` §1, §2, Appendix A; `writeup.md` §5, §9, §9.3;
`scale/records_m1_pilot/README.md`; `git tag -n99 -l 'evidence/*'`.

---

## 26. The patch ran `formcheck` under `--all` and threw the result away

**Not an instance of the family — a plain incompleteness, recorded because the
rule in this file's header applies to every fix.**

The patch added a third mode. It extended the two places that *dispatch* on a
mode and none of the three that *enumerate* them, so under `validate --all`:

1. **`_run_all` computed the formcheck sub-result and dropped it.** Lines 304-306
   ran gold, formcheck and setup; the returned row carried `"gold"` and
   `"setup"` only. The aggregate verdict was still correct — `_all_reason` and
   `_all_error` read all three rows — but the formcheck detail was executed at
   full cost and then discarded before persistence.
2. **`summarize` iterated `("gold", "setup")`**, so the per-check breakdown could
   not have shown formcheck even if the row had carried it.
3. **The run banner said `gold+setup`** when three checks were running.

All three are now `("gold", "formcheck", "setup")` in the same order they
execute. Verified rather than asserted: `summarize` was driven with a row shaped
as `_run_all` now returns and its `checks` key contains a correctly counted
`formcheck` entry; the regenerated patch applies cleanly to a fresh worktree at
`04b0bf5` and reproduces the working checkout byte for byte in all three files.

**Why it survived review.** `scale/run.py` calls `_run_check(task, cfg,
"formcheck")` directly and never reaches `_run_all`, `summarize` or the banner,
so the entire 500-task run exercised none of the three broken sites. The harness
that produced every number in `REPORT.md` could not have caught this, and no
number in it is affected. The lesson is narrow and worth stating anyway: *the
code path your own harness takes is not the code path a user takes*, and a patch
proposing a new mode is read by its recipient along the second one.

Patch size moved with the fix: **+52 −9 across 3 files** (was +49 −7);
`writeup.md` §5 and its appendix updated, since both quoted the old figure.

`verifiers/v1/cli/validate.py` (`_run_all`, `summarize`, `run_validate`);
`verifiers-formcheck.patch`.

---

## 27. The graded memo could not see a test-side change — the tenth of the family

**Bug.** `SweBenchFormcheckTask._tree_digest` hashed `FORMCHECK_TARGETS` and
nothing else. `graded_report` memoizes the whole grading on that digest, so the
key described the production files a transform rewrites and said nothing about
the files the suite is actually made of.

That was sound for every run this repository has taken. In the detection family a
transform rewrites the solution and never the graded tests — `_READ_TREE` excludes
the test tree, `formcheck_write` can only write paths `formcheck_read` returned,
and `f2_operators` states the same rule from the operator's side. The test files
were constant, so hashing them would have been dead weight, and the docstring said
so in as many words: *"Only the targets are ever modified."*

It stops being true the moment a test-side overlay exists. An overlay changes a
graded test file and, by construction, **no target**. The digest is therefore
identical across the overlaid and un-overlaid trees, `graded_report` reports
`memo_hit` and returns the un-overlaid grading, and the row records a reward for a
suite that never ran in the form being claimed. On an overlay meant to *fix* a
coupled test that reads as reward 0.0 — the overlay looking like it did nothing —
and on an overlay applied after a control run it reads as reward 1.0. Both are the
memo answering a question it was never asked.

**This is the same shape as the previous nine, and as D2 specifically: a check
that reports a verdict for a reason invisible in its own output.** The only
evidence of it in a record would be `digest_trace` — two entries with the same
digest and `memo_hit: true` — which is exactly the tell D2 forced into the record
and the reason it is there. The verdict and the reward cannot discriminate. It is
also the same *cause* as D2 twice over: a key that fails to distinguish two trees
it must distinguish, arrived at not by a coding error but by a statement about the
system that was true when written and stopped being true when the system grew.

**Rule.** The digest covers every file whose content can change what the graded
run reports, and it is keyed on **the same list the run actually executes**:
`_digest_paths()` returns `FORMCHECK_TARGETS + spec["test_files"]`, and
`spec["test_files"]` is the list `formcheck_graded` runs and `test_invocation`
turns into the runner's directives. Deriving it from a second, parallel notion of
"the test files" is the cross-path inference `writeup.md` 4.1 warns about; there
is one list.

Every guard D2 installed is preserved and now applies to the wider set: one
`sha256sum`-or-`MISSING` line per path, a raise if the line count disagrees, a
raise on an all-`MISSING` result. The degenerate-case message now reads *"every
digested path is missing"*, since "target" no longer names the whole set.

**Found by inspection, before the overlay was built, not by a wrong number** —
`repair/CONTEXT.md` §4.3, written during reconnaissance for repair-M0a. No number
in `REPORT.md` is affected. The widened digest is a different *value* — it hashes
more lines — but the same *equivalence relation* over the trees the 500-task run
actually produced: that run varied no test file, so every pair of trees that
hashed equal before hashes equal now, and every pair that differed still differs.
Memo hits, verdicts and rewards are unchanged on all 500. What the entry
records is a fix landing *before* the first measurement that could have been
corrupted by it, which is the only time this family has ever been caught early.

**Regression, and it fails against the old code.**
`scale/test_digest.py::test_digest_varies_with_the_graded_test_files` builds two
trees with identical targets and one differing graded test file and asserts the
digests differ. Its stub `sh` reads the paths **out of the digest script** rather
than being handed them, so a path the implementation never asks about never
reaches the hash — without that it would restate the fix instead of testing it.
`test_memo_re_runs_when_only_the_test_file_changed` drives the real
`graded_report` three times and counts `runtime.run` calls: re-run after the
overlay, and still a memo hit on the unchanged tree, because widening a key into
"never memoize" would double the container time of all 500 tasks. Counting the
calls rather than reading the reward is deliberate — both gradings return the same
reward, so the reward cannot tell a re-run from a memo hit, which is precisely why
D2 was invisible. Before the fix: 6/8. After: 8/8; full fast suite 92/92.

`scale/container_task.py` (`_digest_paths`, `_tree_digest`);
`scale/test_digest.py`; `repair/CONTEXT.md` §4.3.

---

## 28. Two gate defects on the first django task, both of the family

Neither is in the detection path — both are in `repair/gate.py`, the two-condition
repair gate — and both are recorded because they returned a verdict for a reason
invisible in the verdict.

**D1 — an incomplete rename read exactly like a failed repair.** `m0d_gate`
listed `django/db/models/deletion.py` as the only file to rename `Collector` in.
It is referenced from **five** django modules, so renaming one of them broke
django itself rather than performing an alpha-rename. Every variant then failed
to import — including the *repaired* one, which no longer mentions the symbol at
all — and every cell read `0.0 / F2P 0/1 / P2P 0/40`. That is precisely the
output a genuinely failed repair produces. It was caught only because the
`import_local` diagnostic recovered *nothing*, which cannot happen if the import
line is the coupling: the number was wrong in a way the gate could not report.

`gate.build` now greps production sources for the old name after applying the
rename and raises on any residue, naming the files. Confirmed against the real
operator afterwards, on a code path that did not produce the config:
`detail.files_changed` lists the same five files and `references_rewritten: 9`.
That cross-check is only possible because entry 27's sibling — persisting
`report["detail"]` — put the operator's own account of the transform into the
record.

**D2 — C2 reports CAUGHT for a test that detects nothing.** The condition "a
broken solution still scores 0.0" is read off the **task reward**, which is a
property of the suite. Whether the *repaired test* still discriminates is a
property of the test. They come apart whenever another test covers the same
behaviour.

On `django-11179` the repair deletes a precondition assertion, and the mutant
`bug_nofast` — which disables exactly the code path that precondition pinned —
goes from failing the F2P test (0/1) to passing it (1/1). The task reward is 0.0
under both, because ten other PASS_TO_PASS tests catch the mutant. The gate
printed `bug_nofast reward = 0.0 CAUGHT` for a test that had stopped detecting it.

`report` now computes **detection drift** — any mutant whose F2P breakdown differs
between the original and the repaired test — and prints it separately. It does
not flip the verdict: the reward is what the reward is, and overstating drift as
a failure would be its own inversion. It says what the reward cannot.

Re-run against the two shipped repairs: *"detection drift: none"* on both, every
pre-existing value unchanged. So `xarray-4966` and `astropy-12907` are confirmed
clean by a check that did not exist when they were accepted, which is the only
form of confirmation worth anything here.

**Why both belong in this file.** D1 is a check whose failure mode is a plausible
number; D2 is a check whose success mode is a plausible number. `REPORT.md` §7's
family is "a check that reports a verdict for a reason invisible in its own
output", and these are the same shape one milestone further out — in the machinery
built to *repair* the defect, rather than in the machinery built to detect it.

A third, smaller one is worth a line because the guard that caught it was written
for an earlier milestone and had never fired: `setattr(instance,
model._meta.pk.attname, None)` occurs twice in `deletion.py` — the gold adds it to
the fast path, the slow path always had it — and `gate.edit`'s "anchor must appear
exactly once" check refused rather than editing whichever one `str.replace` found
first. An ambiguous anchor would have produced a mutant of a code path the test
never reaches, reported as a caught mutant.

`repair/gate.py` (`build`, `edit`, `report`, `graded_ids_present`);
`repair/m0d_gate.py`; `repair/M0D_RESULT.md`; `repair/test_repair_m0d.py`.

---

## 29. A repair-note claim generalised from one case; a scan falsified it

**Bug.** `REPAIR.md`, candidate pattern 2, carried this line:

> Also worth recording: on both tasks the coupling was introduced by the
> benchmark's own test patch, not by the upstream project.

It is true of `django-11179`, whose test patch adds both
`from django.db.models.deletion import Collector` and the one call that uses it.
It is **false of `astropy-12907`**, whose test patch adds `cm_4d_expected` and
four `compound_models` entries and never mentions `_cstack` at all — the coupling
import at `test_separable.py:13-14` is the repository's, not the benchmark's.

The claim was written while reading the second task's *repair*, and generalised
from one case to two on a resemblance rather than a check. The two tasks did
share a shape — one module-scope import carrying a whole module down — and the
provenance of that import was assumed to be shared with it. It is a different
property and it did not transfer.

**How it was caught.** Not by review, and not by a number looking wrong: the
sentence is plausible and nothing downstream depended on it yet. It was caught
because the claim was interesting enough to be worth acting on — if the coupling
were an artefact of task construction, that is a bigger finding than anything in
the repair work — and checking it first is a diff scan costing no containers and
no inference. `repair/scan/test_patch_origin.py` classifies all 34 witness
(task, symbol) pairs; `astropy-12907` came back `pre_existing`, and the sentence
was wrong.

**Rule.** A claim that spans more cases than were examined is checked before it is
acted on, and the check is written down as an artifact rather than performed in
the head. Where the check is static — a diff scan, a grep over records — there is
no reason to defer it: this one took ten seconds and the result is now the thing
the repository cites instead of the sentence.

The scan also answered the underlying question, and the answer is **not
established**: the benchmark's test patch adds a reference to the coupled symbol
in 12 of 28 tasks; in the other 16 the symbol appears nowhere in the test patch.
The specific mechanism that made `django-11179` look general — the benchmark
adding a *module-scope import* — is 4 pairs across 3 tasks. Nothing from the scan
has been promoted to `REPORT.md`; it stays in `repair/scan/RESULT.md` as a
measurement without a conclusion.

**Second defect, found while running the scan.** The classifier's import-block
state machine walked only added lines, so a parenthesised import whose head is an
unchanged context line and whose continuation is added read as an *in-test*
reference rather than a module import. `django-12155` is exactly that shape. It
now walks the post-image — context plus added, in order. Caught by hand-checking
five classifications against diffs already read in this session, which is the only
reason it did not silently shift a count.

`REPAIR.md` (candidate pattern 2); `repair/scan/test_patch_origin.py`;
`repair/scan/RESULT.md`.

---

## 30. C3 reported "no drift" using a comparison that could not have seen drift

**Bug.** C3 — added in entry 28, promoted to a first-class condition after it — was
implemented as a comparison of **FAIL_TO_PASS pass/fail counts** between the
original and the repaired test. That is sufficient only when the coupled test
happens to be a F2P test.

It was, on `django-11179`, which is why the implementation looked adequate: the
condition was written against the one case that had produced drift, and that case
could not distinguish "compares the right thing" from "compares a proxy that
happened to move".

On `django-11433` the coupled test is one of **142 PASS_TO_PASS** tests. Under the
deciding mutant its outcome changes, the F2P breakdown does not move at all
(`0/1` under both variants), and the P2P failure count moves from 17 to 16 —
one, inside a number the mutant itself moves by seventeen. **The old C3 would have
printed "no detection drift" on a repair that had just stopped rejecting the
mutant it existed to reject**, and the gate would have returned PASS.

`grade_log`'s `p2p_failing` is no use for this either: it is truncated to ten
entries (entry 27's sibling concern), so the report cannot say *which* tests
failed on any task with more than ten failures.

**Rule.** C3 recomputes the status map from each run's own log and compares the
exact **set** of graded node ids that did not pass. Sets, not counts; node ids,
not aggregates; recomputed, not read from the truncated field. The gate now also
**fails** on drift rather than printing it — entry 28 made it report-only on the
ground that "the reward is what the reward is", which was right while drift was an
observation and wrong once it became a condition.

**What the fix cost, and what it confirmed.** All three earlier gates were re-run
under the new comparison. `xarray-4966` and `astropy-12907` come back
`C3 OK -- no detection drift` with **every pre-existing value unchanged**, so the
two shipped repairs survive a check strictly stronger than the one they were
accepted under. `django-11179` comes back `C3 FAIL`, naming
`test_fast_delete_instance_set_pk_none` — the same finding entry 28 recorded in
prose, now produced by the gate as a verdict rather than a printed remark.

**Family.** A check reporting a verdict for a reason invisible in its own output —
here the check *is* the reason. C3's whole purpose is to see what the reward
cannot, and it was reading a coarser aggregate of the same run. Written against
one case and generalised without a case that could falsify it, which is
`CHANGES.md` 29 in a different place.

`repair/gate.py` (`failing_ids`, `report`); `repair/m0e_gate.py`;
`repair/M0E_RESULT.md`; `repair/test_repair_m0e.py::test_c3_set_comparison_is_what_catches_this`.

---

## 31. "No containers" was applied to a measurement that needs fifteen of them

**Bug.** The instruction for the next measurement read *"the static measurement,
no containers … this is the second number and it costs nothing"*, applied to
`REPAIR.md` open item 1 — running the `import_local` variant across the 15
all-fail tasks.

That item costs 15 container runs, and `REPAIR.md` §9 says so in its own text:
*"15 container runs, no model, no judgement call"*. The generalisation went from
**no inference** — which is true of it, and is the property that made it
attractive — to **no Docker**, which is not. The two had travelled together on the
preceding measurement (`repair/scan/test_patch_origin.py`, a pure diff scan), and
the second property was carried across with the first.

**How it was caught.** By reading the section the instruction cited before acting
on it. The tell was mechanical rather than clever: the item's own cost line
contradicted the premise in the sentence pointing at it.

**Rule.** When an instruction names a prior artifact, the artifact is read before
the work starts, and a contradiction between the two is raised rather than
resolved silently in either direction. Resolving it silently is the failure mode
in both directions: running 15 containers under "costs nothing" spends the budget
the constraint was protecting, and substituting a cheaper measurement under the
same name reports a different number against the original question.

What was delivered instead was the part the recorded logs already settle — zero
of 795 graded tests executed on any of the 15, so the mechanism is a module-import
failure in every case — reported explicitly as *not* the `import_local` fraction,
with the container cost of the real thing restated.

---

## 32. A `grep -v` filter swallowed the row it was filtering for

**Bug.** Terminal readings of two scans were filtered through
`grep -v "Warning\|cached\|httpx\|HTTP"` to strip HTTP request logging from the
`datasets` library. One witness symbol is **`HTTPDigestAuth`**, so
`psf__requests-1766` was removed from both displayed tables by the filter that
was supposed to be removing noise.

The underlying data was never affected — both scans wrote JSON, and the counts
printed alongside the tables were computed from the full row set, which is why the
tables and their own totals disagreed.

**The part worth keeping.** It was noticed the first time, and dismissed: the row
was recorded as *"a display artefact"* and not chased, on the reasoning that the
count was right so the data was right. That reasoning is correct and beside the
point. A table that disagrees with its own total is a signal that something
between the data and the reader is wrong, and the cost of finding out was one
command. It took a second occurrence, on a different scan, before it was chased —
and the cause was a filter written by the same hand that then read the output
through it.

**Rule.** The JSON is written unconditionally and the file is the artifact; the
terminal is a view of it. A filter applied to output is part of the measurement
apparatus and can corrupt a reading exactly as a parser can — `CHANGES.md` 18 is
the same shape one layer down, where a log parser that understood one runner
silently converted four real witnesses into "invalid transform".

**Family.** A check reporting a verdict for a reason invisible in its own output.
Here the invisible reason was in the pipe, not the program, and the output it
corrupted was the one being used to decide what to do next.

`repair/scan/test_patch_origin.py`; `repair/scan/allfail_mechanism.py`;
`repair/scan/RESULT.md`.

---

## 33. Two branches of the rename operator searched for a substring

**Bug.** `SymbolRename.apply` collects AST spans and rewrites them, which is
boundary-correct for `ast.Name` because a Name's `id` must equal the symbol
exactly. Two branches did not use spans:

    f2_operators.py  ImportFrom  col = line.index(name)
    f2_operators.py  Attribute   col = line.find(name, node.value.end_col_offset)

`str.index` is a substring search. On `from pkg.mod import BaseFoo, Foo` with
anchor `Foo` it returns the offset inside `BaseFoo`, and the operator rewrote
`BaseFoo` while leaving the real `Foo` alias alone. The span check that follows
cannot catch it: `ln[c0:c1]` is exactly `name`, being the tail of the superstring
the search landed in.

**Why it could not be seen in the results.** A task hit this way had its
definition renamed and its import left behind, which fails with `cannot import
name '<anchor>'` — text that names the anchor, so `names_symbol` read it as
coupling and the row came back `WITNESS`. In the records a witness produced by a
broken rename and a witness produced by a coupled grader are the same bytes.
`references_rewritten` counts the same either way. Nothing in the output of the
check could distinguish them, which is the family shape exactly, and it is why
the blast radius could not be settled by reading the 500 records and had to be
measured by re-running.

**The invariant, added before the fix.** An alpha-rename replaces whole
occurrences of `name` with `name__renamed` and changes nothing else, so
substituting the new identifier back on a word boundary must reproduce the input
byte for byte. Anything else is `Refused`. It went in *before* the two branches
were repaired, and was shown firing on the two corrupting shapes — installed
after the fix it would have passed on every case from its first run, and a guard
that has never fired is entry 19.

Two weaker checks were written first and each failed on the case it was written
for. Stripping `name + "__renamed"` and looking for a leftover `"__renamed"`
passes on `BaseFoo__renamed`, which *contains* `Foo__renamed` — the defect being
probed, reproduced inside the probe for it. A token scan for the suffix misses
`Foo__renamedlib`, where the edit landed inside a module path.

**Blast radius, measured.** Each of the 28 witness tasks' production trees was
rebuilt offline — base commit + `tests.diff` + `gold.diff` — and `SymbolRename`
applied twice: at `189451b`, the code that produced the published run, and at
HEAD. The recorded rename was well-formed iff the two agree byte for byte. **All
34 rows across all 28 tasks stand. None void, none undetermined.**

The defect needs the anchor to appear as a substring earlier on the same import
line, before the alias or inside the module path, and no such line exists across
the 28. The near miss is the shape that looks worst and is not: `class
DatabaseClient(BaseDatabaseClient)` in three django tasks, where the superstring
is on the `class` line and reached through the `ClassDef` branch, while the
import line names only `BaseDatabaseClient` — not the anchor, so the `ImportFrom`
branch never fires.

**Why that is a result and not a tautology.** A measurement that puts every row
in one bucket says nothing until the other buckets are shown to be reachable.
The first run of this scan produced the same 34/34 and was not reported, because
as it stood it could not be told apart from a scan incapable of saying anything
else. Three checks were added and all three had to pass before a table was
printed:

* **A positive control**, run first. Two shapes the old operator provably
  corrupts go through the same comparison the 34 rows go through. Both must come
  back void or the scan aborts instead of printing. They do.
* **Every row rewrote real files** — 1, 2, 3, 5 and 11 across the 34. Two
  operators agreeing on a tree neither of them touched is evidence about the
  reconstruction, not about a rename, so that case is bucketed undetermined
  rather than as a witness standing.
* **The rewrite compared is the recorded one.** Applying the old operator to the
  rebuilt tree reproduces the `tree_digest` that row recorded, on **34 of 34
  rows**. The trees are byte-identical to the ones the run saw. A row failing
  this is moved to undetermined, because the comparison would then be between
  something else and the corrected operator.

**Two limits, stated rather than left to be assumed.** The invariant compares
against the input, not against a complete rename, so it catches an edit that
landed in the wrong place and not an edit that never happened. And the scan
covers the 34 witness rows only: the 466 non-witness rows are unaudited, and
there this defect biases toward *fewer* witnesses, not more — a corrupted
rewrite pushes a row away from `WITNESS`, which is the direction nobody audits
and the shape entry 15 already records.

**Rule.** A substitution that has a boundary-aware form available does not use a
substring search, and an operator that claims to preserve a property checks that
property on its own output. Where the check can only be written after the defect
is known, it goes in before the fix and is shown firing, because the fix removes
the evidence that it works.

`repro/f2_operators.py` (`SymbolRename.apply`);
`repair/scan/operator_boundary_probe.py`; `repair/scan/blast_radius_28.py`;
`repair/scan/BLAST_RADIUS_28.md`; `repair/scan/BLAST_RADIUS_28.json`.
