# repair — can a form-coupled reward be repaired, and how would you know?

`REPORT.md` measures how often a task's reward rejects a behaviour-preserving
rewrite: **28 of 126 controlled SWE-bench Verified tasks, 22.2%**. This document
covers the other half of the question. Given a task whose reward is coupled to
the form of the gold patch, can the coupled test be rewritten so the reward stops
rejecting correct solutions — and can that be established rather than asserted?

Four of the 28 were attempted. Two were repaired. Two were not, and each got a
named verdict rather than a shrug.

**The result of this milestone is not the two repairs.** It is that the condition
which decides whether a repair is real was itself falsified, on a case it was not
written against, and strengthened — and that both shipped repairs survive the
stronger version with every recorded value unchanged. A repair method whose
acceptance test has never been wrong has not been tested; this one has been, once,
and the two acceptances that predate the fix were re-derived under it rather than
grandfathered.

---

## Contents

| | |
|---|---|
| [1. The method](#1-the-method) | an entry point, three conditions, a named verdict |
| [2. The three conditions](#2-the-three-conditions) | C1 decoupling, C2 not emptied, C3 detection drift |
| [3. The outcome classes](#3-the-outcome-classes) | four tasks, three classes, n per class |
| [4. Where the failures come from](#4-where-the-failures-come-from) | one import line, not one coupled test per failure |
| [5. What formcheck cannot do here](#5-what-formcheck-cannot-do-here) | CLEAN on a repair that fails C3, twice |
| [6. C3's own status](#6-c3s-own-status) | rewritten once, the least settled part |
| [7. The limit that recurs](#7-the-limit-that-recurs-in-every-case) | the new entry point is never probed |
| [8. What is untried](#8-what-is-untried) | 24 of 28 |
| [9. What was not done, and why](#9-what-was-not-done-and-why) | one refusal, one unmeasured number |

---

## 1. The method

A coupled test names an internal symbol. The repair proposes a different **entry
point** — a way for the test to reach the same behaviour without naming that
symbol — and leaves the assertions alone wherever possible. Three executable
conditions then decide whether the result is a repair.

The proposal is delivered as a **test-side overlay**: a unified diff applied
between the task's test patch and its gold patch, inside the task's own image.
The overlay may only modify files the test patch already touches and may not
touch production Python; `container_task.check_tests_overlay` enforces both and
refuses the run otherwise, because an overlay able to reach a source file could
put the solution into the tree under the guise of repairing a test, and the 1.0
that came back would be indistinguishable from an honest one.

**Node ids may not change.** `test_failed` counts a graded node id absent from the
log as a *failure*, so renaming a test, its class, its module or its
`parametrize` ids pins the reward at 0.0 regardless of what the test does. Every
repair here preserves them exactly.

When no formulation satisfies the three conditions, the task gets a **named
verdict** — §3 — and the candidate diff is kept as the evidence for that verdict
rather than applied.

---

## 2. The three conditions

| | | read off |
|---|---|---|
| **C1** | the renamed gold scores **1.0** — the coupling is gone | the task reward |
| **C2** | behavioural mutants still score **0.0** — the suite was not emptied | the task reward |
| **C3** | for every mutant, the repaired test rejects **exactly the set** of graded tests the original rejected | the per-node-id outcome set |

No two are sufficient. A test asserting nothing passes C1 and fails C2. The
original coupled test passes C2 and fails C1. And a repair that guts one test
passes C1 **and** C2 whenever any sibling test happens to cover the same mutant —
which is what C3 exists to catch, and what it caught twice.

C1 and C2 are properties of the **suite**. C3 is a property of the **test**. They
come apart precisely when other tests overlap the same behaviour, which is common
and more common in large suites.

**A condition that fires on failure cannot discriminate a broken apparatus from a
real negative.** A reward of 0.0 is compatible with both, so any check whose pass
*is* a 0.0 is satisfied by a tree that never ran. That happened here: on
`django-11179`'s first run the rename covered one of five referencing files, the
library did not import, and every cell read 0.0 — C2 read all three mutants as
CAUGHT and the overlay's positive control was green, over a tree in which nothing
executed. What separated it from a correct rename was **C1**, the renamed gold
*recovering* to 1.0, which a broken tree cannot do. The residue grep was added
afterwards, in response to that run, and it closes the incomplete-rename case
only: it cannot see a rename corrupted the other way, because `\bCollector\b` does
not occur inside `NoFastDeleteCollector__renamed` (`CHANGES.md` 34). A check
written against one failure is not thereby a check on the apparatus. The same
shape is what stopped the `import_local` run, whose control must reproduce the
witness and whose `recovery == 0` is a defect rather than a measurement.

What follows for the method is that **every gate needs at least one condition
whose pass requires the apparatus to work**, and C1 is currently the only one
here that does. C2 and C3 are both satisfiable by a suite that did not run. C3
compares the failing sets of the original and the repaired run, and `failing_ids`
counts a graded id absent from the log as failing — so a suite that never
executed yields *every* id on both sides, two identical full sets, which compare
equal and read as no drift. The graded-node-id count below is a patch over that
for C2 specifically, not a general answer. This is an
observation over n=2, not a law: two occurrences of one shape, on one task each,
and the second was recognised only because the first had been written down.

Three constraints on C2, each of which a shortcut would quietly violate:

* **The breakage must be behavioural, with identifiers intact.** A mutant that
  breaks an import fails the repaired test for the same coupled reason as before
  and re-measures the defect instead of testing the repair. The gate asserts no
  mutant's failure names the symbol — false on all mutant runs, all four tasks.
* **The mutants run against every test variant, including the original.** "The
  repair did not weaken detection" is a comparison; a mutant the original test
  also missed says nothing.
* **The mutant must actually have run the graded suite.** `test_failed` scores a
  node id absent from the log identically to one that ran and failed — one
  expression, `case not in sm or sm[case] in [FAILED, ERROR]`, both branches. A
  mutant that breaks module import therefore scores 0.0 with zero graded ids
  reported and would read as CAUGHT. The gate records how many graded node ids
  each run reported and requires every mutant to match the gold.

Grading throughout is `repro/m4_grader.grade_log` — the same offline
SWE-bench-format grader the 500-task run used, over the dataset's own F2P/P2P
lists. No verdict is read off pytest output by eye.

---

## 3. The outcome classes

Four tasks, **three** classes: one in which repair succeeded and two in which it
did not. Each class is named for what makes it that class, not for the task.

| class | tasks | n | outcome |
|---|---|---|---|
| **entry-point substitution** | `pydata/xarray-4966`, `astropy/astropy-12907` | 2 | repaired, shipped |
| **PRECONDITION** | `django/django-11179` | 1 | not repairable at the test level |
| **HOLLOWING-OUT** | `django/django-11433` | 1 | repair available and wrong |

### Entry-point substitution — n = 2

The coupled line is a **route** to the behaviour under test, and an exported
symbol reaches the same behaviour with the same discriminating power. The
assertions do not change.

On `xarray-4966` the two coupled tests constructed an internal class by name:

```diff
-    coder = variables.UnsignedIntegerCoder()
-    decoded = coder.decode(encoded)
+    decoded = xr.decode_cf(xr.Dataset({"v": encoded}))["v"]
```

`decode_cf` is in `xarray/__init__.py`'s `__all__`. The two `assert` lines were
already the issue's contract and were left untouched.

On `astropy-12907` the substitution was cleaner still — the expected matrices are
**byte-identical** before and after, and only the call changed, from
`_cstack(sh1, rot)` to `separability_matrix(sh1 & rot)`. `separability_matrix` is
one of the two names in that module's `__all__`; `_cstack` is the private function
behind the `&` operator it uses. Checked numerically before the repair was
written, for all three cases.

Both pass C1, C2 and C3. Both were accepted before C3 existed and re-derived
under it (§6).

### PRECONDITION — n = 1

The coupled line does not route to the behaviour under test. It **pins that a
particular code path runs**.

```python
u = User.objects.create()
collector = Collector(using='default')            # the coupled lines
self.assertTrue(collector.can_fast_delete(u))     # a PRECONDITION
u.delete()
self.assertIsNone(u.pk)                           # the contract -- never coupled
```

The gold patch fixes the *fast* delete path only; the slow path has always been
correct. The precondition is what makes this a test of the fixed path.
`Collector` is not public — no `__all__` entry in `django/db/models/deletion.py`,
not re-exported from `django.db.models` — so there is no route to substitute, and
the coupled line is not a route.

A behavioural substitute was **measured, not argued**. The natural candidate is a
query count. With `can_fast_delete` forced to return `False`, the delete still
issues one query, the same SQL, and still nulls the pk: after the gold patch the
two paths are observationally equivalent for this input, so `assertNumQueries(1)`
separates nothing.

**Recognition test.** Removing the coupled line leaves every assertion still
passing on the gold, *and* there is a behavioural mutant the removal stops the
test catching. Here that mutant is `bug_nofast`: F2P 0/1 → 1/1 under the
candidate repair.

### HOLLOWING-OUT — n = 1

A public route exists and reaches the same **assertion** through different
**code**. Measured in-image before the repair was written:

| | `cleaned_data` | mechanism | `instance.name` |
|---|---|---|---|
| coupled test | `{'name': 'John Doe'}` | the `fields=()` filter suppresses it | `''` |
| public route | `{}` | the field never reached `cleaned_data` | `''` |

The mutant `bug_fieldfilter` inverts that filter. The original test rejects it;
the repaired test does not; the task reward is 0.0 under both, because seventeen
other graded tests reject it too.

**Recognition test.** The repair passes C1 and C2 and there exists a behavioural
mutant whose rejection set loses the coupled test. C3 is the only one of the four
available checks — C1, C2, C3, formcheck — that sees it.

**Why it is distinct from PRECONDITION.** In PRECONDITION no substitute exists and
every candidate is provably vacuous: the repair is *unavailable*. In
hollowing-out a substitute exists, passes every reward-level check, and is
*wrong*. The first is a wall; the second is a trap, and it is the more dangerous
of the two, because the gate in force before this milestone would have shipped it.

**Telling them apart before running anything.** Ask what the public route makes
true. Same assertion by the same code — entry-point substitution. Same assertion
by different code — expect hollowing-out, and name the mutant that distinguishes
the two paths. On `django-11433` that prediction was made from a probe measuring
`cleaned_data` under both routes, and C3 confirmed it.

---

## 4. Where the failures come from

`REPORT.md` §3(a) reports that in 15 of the 28 tasks *every* graded test fails
under the rename. That is a measurement of **reward damage**. It is not a
measurement of how many of a suite's tests actually reference the symbol, and the
two are equal only if every failing test names it.

At module scope they are not equal. A third test variant — `import_local`, which
changes nothing except *where* the symbol is imported — separates them:

| task | runner | under the rename, `import_local` recovers | tests using the symbol |
|---|---|---|---|
| `astropy-12907` | pytest | **14 of 15** | 1 of 6 test functions |
| `django-11179` | `runtests.py` | **40 of 41** | 1 of 42 test methods |
| `django-11433` | `runtests.py` | **142 of 143** | 1 of 144 test methods |

**n = 3, three repos, two test runners.** In each case one module-scope
`from … import` naming one symbol takes down the entire module, and in each case
the residual is the single test whose *subject* is that symbol — which no
placement of an import can save. `import_local` still scores **0.0** on all three,
which is exactly why the reward cannot distinguish these two situations and why
the distinction had to be measured separately.

On all three the task's own FAIL_TO_PASS tests — the ones the issue is about —
reach the code through public API and are pure collateral.

Two further facts about these 28, both measured statically over the task diffs
(`repair/scan/RESULT.md`):

* In **16 of 28** the coupled symbol appears **nowhere in the task's test patch**.
  The reference is the repository's own. Whatever the benchmark introduces, the
  majority of this coupling is not an artefact of task construction and cannot be
  removed by generating tasks differently.
* The benchmark adds a **module-scope import** — the mechanism above — in 4
  (task, symbol) pairs across 3 tasks. It is not the common case.

---

## 5. What formcheck cannot do here

**`formcheck` reported CLEAN on a repair that fails C3. Twice** — `django-11179`
and `django-11433`, both times with reward 1.0 on a tree genuinely carrying the
rename, and no witnesses on the record.

That is not a defect in `formcheck`. It answers "does this reward reject a
behaviour-preserving rewrite", and after both candidate repairs the answer is
honestly no. It does not answer "does this test still test anything", and nothing
in it could.

The operational consequence is the whole reason C3 exists:

> **Detection passing is not repair passing.** A repair that turns WITNESS into
> CLEAN has demonstrated only that the reward stopped rejecting the rename. It has
> not demonstrated that the suite still rejects wrong programs, and on 2 of the 4
> tasks attempted it did not.

---

## 6. C3's own status

**C3 has been rewritten once, on n = 2 of observed drift, and it is the least
settled part of this method.** It is presented here as a condition that has been
wrong once, not as a finished one.

It was added after `django-11179`, where a candidate repair passed C1 and C2 and
was still strictly weaker than the test it replaced. It was implemented as a
comparison of FAIL_TO_PASS pass/fail counts — adequate for that task, where the
coupled test is the F2P test, and **written against the only case that had ever
produced drift**.

`django-11433` falsified it. There the coupled test is one of 142 PASS_TO_PASS
tests: under the deciding mutant its outcome changes, the F2P breakdown does not
move at all, and the P2P failure count moves from 17 to 16 — one, inside a number
the mutant itself moves by seventeen. The count-based C3 would have printed *"no
detection drift"* on a repair that had just stopped rejecting the mutant it
existed to reject.

C3 now recomputes the status map from each run's own log and compares the exact
**set** of graded node ids that did not pass. Sets, not counts; node ids, not
aggregates; recomputed, not read from `grade_log`'s `p2p_failing`, which is
truncated to ten entries. It also **fails the gate** rather than printing a
remark, which it did not do when it was an observation.

**Both shipped repairs were re-derived under the stronger version.**
`xarray-4966` and `astropy-12907` come back `C3 OK — no detection drift` with
**every pre-existing value unchanged**; `django-11179` comes back `C3 FAIL`,
naming `test_fast_delete_instance_set_pk_none`. Neither acceptance was
grandfathered.

Two rewrites of the same condition on two cases is not a settled acceptance test.
It is one that has been falsified once and has not yet met a third kind of drift.

**All four gates were re-run under the boundary-aware substitution**
(`CHANGES.md` 34), against the recorded result of each, and **every recorded
value is unchanged** — zero differing leaves in all four result files, which the
re-run reproduced byte for byte. No verdict moved: `m0b` and `m0c` `PASS` with
`C3 OK`, `m0d` and `m0e` `FAIL` with `C3` naming the same drifting test as
before. The result files hold the fifteen measured cells and the conditions are
computed from them, so equality of the cells is equality of the verdicts.

Three of the four could not have moved and that is a proof rather than a
re-run: for `m0b`, `m0c` and `m0e`, the old substitution and the boundary-aware
one produce byte-identical output on every production file the gate renames.
Only `m0d` differed, in one file of five — `str.replace` had rewritten
`NoFastDeleteCollector` along with `Collector`. It changed nothing measurable,
because the identifier is defined and used only in that file and was rewritten
consistently in both places. That is luck rather than design, and it is the
reason the substitution is fixed rather than left alone.

---

## 7. The limit that recurs in every case

`formcheck` offers an operator only symbols whose definition the gold patch
overlaps (`writeup.md` §3.3, `scale/SCOPE.md`). A repair moves the test onto a
**new** entry point — `decode_cf`, `separability_matrix`, `modelform_factory` —
and that symbol is, by construction, not one the gold patch touched. **It is never
probed, on any task, before or after.**

So "the coupling did not move" is never a `formcheck` verdict here. On the two
shipped repairs it rests on two checkable facts, both asserted in the test suite:

1. the new entry point is exported — `decode_cf` in `xarray/__init__.py`'s
   `__all__` at line 55; `separability_matrix` in
   `astropy/modeling/separable.py`'s `__all__` at line 24;
2. the repaired test bodies name no module-internal symbol at all.

The obvious fix — an operator that anchors on public re-exports — is refused, and
the refusal is §9.

**This is a property of the method, not of any task.** Every repair of this kind
ends with an unprobed new entry point, and each one is argued rather than
measured.

---

## 8. What is untried

Four of the 28 witness tasks were attempted. **24 were not.**

| | |
|---|---|
| attempted | 4 — xarray-4966, astropy-12907, django-11179, django-11433 |
| untried | **24** |
| of those, django | **12** |
| of those django, the module-attribute shape rather than the import shape | **4** — django-13212, django-14311, django-14771, django-15572 |

Django is 14 of the 28 and the two attempted both failed C3, by two different
mechanisms. Neither failure is django-specific: the runner was cleared —
the positive control lands and is scoped on both, and all three conditions stay
evaluable — and both obstacles are graded suites that unit-test internal helpers,
which is a property of the tests. **Two tasks do not establish a rate for a
stratum of fourteen**, and no rate is offered.

The four repos with a single witness task each — `psf/requests`, `sympy/sympy`,
plus the untried `pytest-dev/pytest` and `scikit-learn` cases — are untried
entirely.

---

## 9. What was not done, and why

**An operator anchoring on public re-exports.** It would close §7 by probing the
symbol a repair moves to. It is refused because widening the anchor rule to reach
a symbol this project has just introduced is selecting for the outcome —
`scale/SCOPE.md` exists because that already happened once, and the rule was
deliberately not widened to bring a known-interesting row back. It is also a scope
change with consequences beyond repair: a public-re-export operator changes what
`formcheck` measures, and therefore the denominator of the headline number. Doing
it honestly means fixing what the operator anchors on **before** seeing which
symbols it admits, on the same before-the-results discipline as
`scale/STOPPING_RULE.md`, then running it across all 500.

**The attributable-to-one-import fraction across the 15 — MEASURED, and it does
not generalise.** §4 established the mechanism at n = 3. The `import_local`
variant has now been run on the other 12 (`repair/scan/IMPORT_LOCAL_RESULT.md`,
13 measurements over 12 tasks), and §4's shape — one module-scope import taking
down the whole module, with the single residual being the test whose *subject* is
the symbol, `k = 1` — **holds on 3 of the 9 measured.** It is one shape among
several, and it was the first three seen.

Six come back `k > 1` and are listed rather than averaged. Two of them invert the
picture: `django-15380` and `django-15973` still fail 122 of 134 and 146 of 158
graded tests once the import is moved, so nearly the whole suite genuinely
reaches `MigrationAutodetector` and only about 9% of the loss is attributable to
the import line. On those two, reward damage and coupling extent nearly coincide,
which is the opposite of what §4's three cases show. Two more are a fourth
outcome, `HELPER_COUPLED`: every graded test reaches the symbol through a shared
helper, so recovery is genuinely 0 and no placement of the import can change it.

**No central tendency is reported, and none should be constructed.** The
attributable fraction varies by task from **7.6%** (`django-15973`) to **99.1%**
(`scikit-learn-14983`) — an order of magnitude — and the two ends are different
mechanisms rather than two samples of one quantity. A mean over the `k = 1` rows
would be worse than uninformative: selecting `k = 1` fixes `recovery = N − 1`, so
any such ratio is high by construction and says only how large those `N` are.
The per-task table is the measurement; the range is the finding.

**Open item 1 is closed.** Two corrections it earned on the way. It was at one
point described as costing nothing and needing no containers — it is not, and
`CHANGES.md` 31 records the generalisation that produced that; it cost one image
pull and one container per measurement, thirteen of them, plus a fourteenth from
the duplicate in `CHANGES.md` 36. And the first attempt was void, on a defect in
the rename it depended on (`CHANGES.md` 34).

It is not a repair and must not be reported as one: `import_local` scores 0.0 on
every task where any test genuinely names the symbol, which is every task it has
been run on.

---

## Artifacts

| | |
|---|---|
| `repair/gate.py` | the three-condition gate; `m0b`–`m0e_gate.py` are configs over it |
| `repair/M0A_RESULT.md` | the overlay surface lands, proven neutrally with an inert overlay, before any repair claim is attached to it |
| `repair/M0B_RESULT.md` … `M0E_RESULT.md` | one per task, with the full matrices |
| `repair/overlay_*.diff` | positive controls, `import_local` diagnostics, repairs |
| `repair/records_m0*/` | the harness runs behind every claim |
| `repair/test_repair_m0*.py` | all of it pinned offline, in the fast gate |
| `repair/scan/RESULT.md` | the static diff scan behind §4 |
| `repair/scan/IMPORT_LOCAL_RESULT.md` | the `import_local` measurement across the 12, closing §9 open item 1 |
| `repair/scan/BLAST_RADIUS_28.md` | the boundary-defect audit across all 34 witness rows |
| `repair/scan/PARSER_SWALLOW_RESULT.md` | the swallowed-status-line scan over the run's stored logs |
| `CHANGES.md` 27–36 | the defects this milestone found in its own machinery |

**A note on `scale/progress.jsonl`.** The M0 runs appended **14 single-task
segments** to the file that already held the published run's telemetry, so its
`done` events now total **407** rather than 393. Nothing published draws from
this file — `REPORT.md`'s figures come from `scale/records_m4/` and
`summary.json` — and the segments are delimited by `run_start`/`run_end`, so they
separate cleanly. It is recorded here rather than tidied away: editing published
telemetry so that a count comes out round is a worse thing to do than explaining
why the count is what it is.
