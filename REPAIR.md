# REPAIR — what repairing a form-coupled reward actually takes

`REPORT.md` measures how often a task's reward rejects a behaviour-preserving
rewrite: 28 of 126 controlled tasks, 22.2%. This file is the other half — what it
takes to repair one, what generalises, and what is still unknown.

The discipline of `CHANGES.md` applies: an entry is written when a result forces
it, and it says what would have been claimed wrongly without it. Nothing here is
a rule until more than one case has produced it.

---

## Candidate pattern 1 — the coupling may live in how the test *reaches* the
## code, not in what it *asserts*

**Status: held on 2 of 3. It failed on the third for a stated, checkable reason
— the pattern now has a known boundary rather than only supporting cases.**

The plan for `pydata__xarray-4966` was to rewrite the coupled assertions. When
the tests were actually read, the assertions turned out to be fine:

```python
assert decoded.dtype == signed_dtype
assert decoded.values == original_values
```

That *is* the issue's contract — `_Unsigned` decoding produces the right dtype
and the right values. Nothing about it names an internal symbol, and nothing
about it needed to change.

The coupled line was the one above it:

```python
coder = variables.UnsignedIntegerCoder()      # the entry point
decoded = coder.decode(encoded)
```

The test reached the behaviour by constructing an internal class **by name**. The
repair was to reach the same behaviour through `xr.decode_cf`, which
`xarray/__init__.py` exports in `__all__`, and to leave both assertions
untouched:

```python
decoded = xr.decode_cf(xr.Dataset({"v": encoded}))["v"]
```

**Why this might generalise.** A test has two surfaces onto the code under test:
what it *asserts* (which the issue usually does specify) and how it *gets there*
(which the issue usually does not). An alpha-rename cannot perturb the first and
routinely breaks the second. If that asymmetry is general, then "repair the
assertion" is the wrong frame for a whole class of these, and the question to ask
of a coupled test is *which surface is coupled* before proposing anything.

**It held on the second case, and more cleanly.** `astropy__astropy-12907` was
picked by criteria fixed in advance — the `from … import` shape, a different
repo, `p2p_coupling`, single-file gold — precisely because that shape might not
have a test body to rewrite at all. It does, and the pattern applies: in
`test_cstack` the assertion expressions are not merely equivalent to the
originals, they are **byte-identical**. Only the call changed, from
`_cstack(sh1, rot)` to `separability_matrix(sh1 & rot)`, and the expected
matrices did not have to be touched. `separability_matrix` is exported in that
module's `__all__`; `_cstack` is the private function behind the `&` operator it
uses. Verified numerically before the repair was written, for all three cases.

**It failed on the third case, and that is the boundary.** On
`django__django-11179` the coupled call is `Collector(using='default')` followed
by `assertTrue(collector.can_fast_delete(u))` — and `Collector` is **not public**:
no `__all__` in `django/db/models/deletion.py`, not re-exported from
`django.db.models`. There is no exported symbol reaching the same behaviour, so
the substitution the pattern prescribes is simply unavailable.

Worse, the coupled line is not an entry point to the behaviour under test at all.
It is a **precondition**: it pins that the *fast* delete path is the one being
exercised, which matters because the gold patch fixes only that path. The
contract assertion (`assertIsNone(u.pk)`) was never coupled. So the pattern's own
distinction — entry point versus assertion — does not partition this test; there
is a third kind of line, and it is the coupled one.

**The refined statement.** The pattern applies when the coupled line is a *route
to the behaviour under test* and an exported route exists. It does not apply when
the coupled line *asserts something about the implementation* that no public
observable reproduces. On `django-11179` a behavioural substitute was looked for
and measured — a query count — and found vacuous: after the gold patch the fast
and slow paths issue the same single query and both null the pk, so
`assertNumQueries(1)` separates nothing.

**What is still not established.** The two repaired tasks happened to have a
public entry point reaching the same behaviour with the same discriminating
power. That is a property of the library, not of the coupling. The remaining
caveats:

* **django is half the corpus and one task of it has been tried.** The runner is
  *not* the obstacle — `repair-M0d` established that the positive control works,
  that the log distinguishes absence from failure, and that both conditions stay
  evaluable. The one django task attempted did not repair cleanly, for a reason
  that is not django-specific. The other 13 are untried.
* **Both cases were `symbol_rename`.** It is the only operator producing
  witnesses, so this is not a limitation of the sample — but the pattern is a
  claim about renames, not about coupling in general.
* Two repos out of nine. `pytest`, `sphinx`, `pylint`, `scikit-learn`, `requests`
  and `sympy` are untried.

**What would confirm or kill it.** A case where the coupled test has no public
entry point reaching the same behaviour. The pattern predicts such a task cannot
be repaired at the test level at all — and if one is found and *is* repairable by
rewriting assertions, the pattern is wrong about which surface matters.

Evidence: `repair/M0B_RESULT.md`, `repair/M0C_RESULT.md`, `repair/gate.py`,
`repair/test_repair_m0b.py`, `repair/test_repair_m0c.py`.

---

## Candidate pattern 2 — at module scope, blast radius is unrelated to how many
## tests are actually coupled

**Status: measured twice, in two repos and two test runners. n = 2.**

`test_separable.py` reaches production code through one module-level import:

```python
from astropy.modeling.separable import (_coord_matrix, is_separable, _cdot,
                                        _cstack, _arith_oper, separability_matrix)
```

`_cstack` is used by **exactly one** of the module's six test functions. Renaming
it fails **all 15** graded tests, because the module stops importing. Both
FAIL_TO_PASS tests — the ones the issue is about — already reach the code through
public API and are pure collateral.

The split was measured rather than argued, with a third test variant
(`import_local`) that changes nothing but where `_cstack` is imported:

| variant, under the rename | F2P | P2P | reward |
|---|---|---|---|
| `original` | 0/2 | 0/13 | 0.0 |
| `import_local` | 2/2 | 12/13 | 0.0 |
| `repaired` | 2/2 | 13/13 | 1.0 |

**14 of 15 failures were the import line.** The 15th is intrinsic: `test_cstack`
is a unit test whose *subject* is the renamed symbol, and no placement of an
import saves a test that calls `_cstack` by name.

Two consequences worth keeping separate:

* **Collateral coupling** is unambiguously a reward defect. Those 14 tests assert
  public behaviour and fail for a name they never mention.
* **Intrinsic coupling** is a judgement. A unit test of a private helper names it
  because that is what it tests. Repairing it means changing what the test enters
  through — defensible here only because `separability_matrix` demonstrably
  computes the same thing for these inputs, checked before the repair was
  written.

**It held on `django__django-11179`, under a different runner.** One module-scope
`from django.db.models.deletion import Collector`, added by the task's own test
patch, used by exactly one of the module's 42 test methods:

| variant, under the rename | F2P | P2P | reward |
|---|---|---|---|
| shipped test module | 0/1 | 0/40 | 0.0 |
| `import_local` | 0/1 | **40/40** | 0.0 |
| `repaired` | 1/1 | 40/40 | 1.0 |

**40 of 41 failures were the import line**, against astropy's 14 of 15. Two
repos, two runners, same shape.

*Correction.* This section previously added that on both tasks the coupling was
introduced by the benchmark's own test patch. That is true of `django-11179` and
**false of `astropy-12907`**, whose test patch never mentions `_cstack` — the
coupling import pre-exists in the repository. The claim was generalised from one
case to two without checking the second. A static scan of all 28 now measures it
properly: `repair/scan/RESULT.md`.

`REPORT.md` §3(a) and the README carry an amendment stating this distinction —
reward damage (measured, on all 28) versus extent of genuine coupling (not
measured) — with astropy's table as its evidence. No number in either document
changed.

**Not repaired, and reported instead:** `_coord_matrix`, `_cdot` and
`_arith_oper` sit in the same import with the identical latent coupling.
`formcheck` never flagged them because the gold patch does not touch them. Fixing
them would be repairing what the harness did not find.

Evidence: `repair/M0C_RESULT.md`,
`test_the_blast_radius_was_almost_entirely_the_import_line`.

---

## Open question 1 — an operator that anchors on public re-exports

**Status: deliberately not done. Logged with the reasoning, not deferred
silently. Recurred identically on the second case.**

After repairing `xarray-4966`, `formcheck` reports no witness. That verdict is
narrower than it looks, and the gap is worth stating precisely.

`formcheck` only offers an operator symbols whose definition the gold patch
overlaps (`writeup.md` §3.3, `scale/SCOPE.md`). This gold patch touches only
`UnsignedIntegerCoder.decode`, so `symbols_covering` yields
`{UnsignedIntegerCoder, decode}` and — since `SymbolRename.anchors` walks
module-level definitions only — `UnsignedIntegerCoder` is the sole anchor, before
and after the repair. **`decode_cf`, the symbol the repair introduced, is not
probed and cannot be.**

So "the coupling did not move" currently rests on two facts, **neither of which
is a `formcheck` verdict**:

1. `xr.decode_cf` is public API — `"decode_cf"` appears in `xarray/__init__.py`'s
   `__all__` at line 55.
2. The two repaired test bodies name no module-internal symbol at all: zero
   occurrences of `UnsignedIntegerCoder`, and no other `variables.*` reference.

Both are checkable and both are checked (`test_the_repaired_test_names_no_
internal_symbol`). Neither is the harness saying "I looked and found nothing."

**The same gap reappeared unchanged on `astropy-12907`.** That gold patch edits
one line inside `_cstack`, so `_cstack` is the only anchor before and after, and
`separability_matrix` — the symbol the repair now depends on — is not probed. The
two supporting facts are the same two: it is exported (`__all__` in
`astropy/modeling/separable.py` line 24), and the repaired test names no private
symbol. This is now a property of the method, not a quirk of one task: **every
repair of this kind will end with an unprobed new entry point**, and each one is
argued rather than measured.

**Why the obvious fix is refused.** The obvious fix is an operator that anchors
on public re-exports, so the new entry point is probed too. It is refused *now*
for a reason that is not about effort:

> Widening the anchor rule in order to reach a symbol this project just
> introduced is selecting for the outcome. `SCOPE.md` exists because that already
> happened once — `MarkDecorator` was in the Phase 2 candidate set because a
> person put it there — and the rule was deliberately **not** widened to bring
> that row back. A rule extended to cover a symbol chosen after the fact would
> still pass every test in the repo and would have lost the property that makes a
> null result mean anything.

It is also a scope change with consequences beyond one task: a public-re-export
operator changes what `formcheck` measures, which changes the denominator of THE
NUMBER, and it would need its own equivalence argument, its own tier, and its own
answer to "what does the oracle observe". That is a milestone, not a patch.

**What it would take to do it honestly.** Fix the widened rule *before* seeing
which symbols it admits, on the same before-the-results discipline as
`scale/STOPPING_RULE.md` — write down what the operator anchors on, commit it,
then run it across all 500 tasks and report what comes back, including on tasks
this project has never repaired.

---

## The three conditions any repair must pass

C1 and C2 were established in `repair-M0b`. **C3 was added in `repair-M0d`, after
a repair passed both of the others and was still strictly weaker than the test it
replaced.** All three are required of every repair from here on.

| | | read off |
|---|---|---|
| **C1** | the renamed gold scores **1.0** — the coupling is gone | the task reward |
| **C2** | genuinely broken solutions still score **0.0** — the suite still rejects wrong programs | the task reward |
| **C3** | **no detection drift** — every mutant's F2P breakdown is identical under the original and the repaired test | the per-test breakdown |

No two of them are sufficient. A test asserting nothing passes C1 and fails C2;
the original coupled test passes C2 and fails C1; and a repair that guts one test
passes C1 and C2 whenever any sibling test happens to cover the same mutant —
which is what C3 exists to catch. C1 and C2 are properties of the **suite**; C3
is a property of the **test**, and that is exactly why the first two cannot
substitute for it.

C3 does not flip the gate's verdict on its own. The reward is what the reward is,
and reporting drift as a failure would be its own inversion — the suite really did
reject the mutant. It is reported separately, and a repair that drifts is not
shipped without saying so.

**`xarray-4966` and `astropy-12907` were confirmed clean by C3 after the fact.**
Both were accepted before the condition existed; re-running their gates under it
reports *"detection drift: none"* with every pre-existing value unchanged. That is
the only form of confirmation worth anything — a check the work did not get to
choose.

Three constraints on C2, each learned the hard way rather than assumed:

* **The breakage must be behavioural, with identifiers intact.** A mutant that
  breaks an import fails the repaired test for the same coupled reason as before
  and proves nothing. `m0b_gate.py` asserts `names_symbol_in_log` is false for
  every mutant run.
* **Run the mutants against the original test too.** "Detection was not weakened"
  is a comparison, not an absolute: a mutant the original test also missed says
  nothing about the repair.
* **Check the digest.** A 1.0 whose tree digest equals the control's is the memo
  answering a question it was never asked (`CHANGES.md` 16, 27), and the verdict
  alone cannot tell that from a real result.

And one on the repair itself: **node ids may not change.** `test_failed` counts a
node id absent from the log as a failure, so renaming a test, its class, its
module or its `parametrize` ids pins the reward at 0.0 regardless of what the
test does (`repair/CONTEXT.md` §3.3).

---

## Outcome class — PRECONDITION coupling

**Status: one task, `django__django-11179`. A verdict, not a failure to repair.**

Two of the three tasks examined had their coupling in a **route**: the test named
an internal symbol in order to reach the behaviour under test, and an exported
symbol reached the same behaviour. Candidate pattern 1 is about those.

`django-11179` is a third kind, and it needs its own name because calling it "a
repair we could not find" would be wrong.

```python
u = User.objects.create()
collector = Collector(using='default')            # the coupled lines
self.assertTrue(collector.can_fast_delete(u))     # a PRECONDITION
u.delete()
self.assertIsNone(u.pk)                           # the contract -- never coupled
```

The coupled line does not route to the behaviour under test. It **pins that a
particular code path runs** — here, that the *fast* delete path is the one being
exercised, which matters because the gold patch fixes only that path and the slow
path has always been correct. The contract assertion was never coupled at all.

**Why pattern 1 cannot apply.** Pattern 1 substitutes one route for another. There
is no route to substitute: the precondition is an assertion *about the
implementation*, and the symbol it names is not public (`Collector` has no
`__all__` entry in `django/db/models/deletion.py` and is not re-exported from
`django.db.models`).

**Why a substitute is vacuous, measured rather than argued.** The natural
behavioural proxy is a query count — a fast delete should be one query. With
`can_fast_delete` forced to return `False`, the delete still issues **one query,
the same SQL, and still nulls the pk**. After the gold patch the two paths are
observationally equivalent for this input, so `assertNumQueries(1)` separates
nothing. Any public observable that could separate them would have to be one the
gold patch made identical.

**The recognition test.** A coupled line is PRECONDITION coupling when removing it
leaves every assertion in the test still passing on the gold, *and* there exists a
behavioural mutant that the removal stops the test from catching. On
`django-11179` that mutant is `bug_nofast`: F2P 0/1 → 1/1 under the repair. This
is exactly what C3 measures, which is why the class and the condition arrived
together.

**What it implies.** A task with PRECONDITION coupling cannot be repaired at the
test level without either weakening the test or leaving the name in place. The
honest options are to leave it, or to change something other than the test — the
graded node-id lists, or the issue's own specification of which path is required.
Both are outside what the overlay surface can do and outside what this project has
argued for.

n = 1. Nothing about it was django-specific.

Evidence: `repair/M0D_RESULT.md`, `repair/test_repair_m0d.py`.

---

## Finding 1 — C2 measured at the reward level cannot detect a hollowing-out

**Status: measured once, on `django__django-11179`. It changes the method, not
just a task.**

The two conditions ask: does the renamed gold score 1.0 (C1), and do broken
solutions still score 0.0 (C2)? Both are read off the **task reward**. On
`django-11179` the candidate repair passes both — and is still strictly weaker
than the test it replaced.

The repair deletes the precondition `assertTrue(collector.can_fast_delete(u))`,
because that is the only line naming the symbol. The mutant `bug_nofast` disables
fast deletion entirely — exactly the regression that precondition existed to
catch:

| | original test | repaired test |
|---|---|---|
| F2P outcome under `bug_nofast` | **0/1 — fails** | **1/1 — passes** |
| task reward | 0.0 | 0.0 |
| P2P failures | 10 | 10 |

The repaired test no longer detects the mutant. The reward is 0.0 anyway, because
**ten other P2P tests catch it**. C2 reads `CAUGHT` for a test that detects
nothing.

**Why this is general.** Reward is a property of the *suite*. "Was this test
weakened" is a property of the *test*. They come apart precisely when other tests
overlap the same behaviour — which is common, and more common in large suites.
A repair that guts a test will be scored CAUGHT by C2 whenever any sibling test
happens to cover the mutant.

It was invisible on `xarray-4966` and `astropy-12907` because in both, every
mutant's F2P breakdown was identical under the original and repaired tests —
there was nothing to see. It took a case where the repair genuinely lost
something to show that the condition could not have told us.

**What changed.** `repair/gate.py` now reports **detection drift** — any mutant
whose F2P breakdown differs between the original and repaired tests — separately
from C2. It does not flip the verdict, because the reward is what the reward is;
it says what the reward cannot. Re-run against M0b and M0c: *"detection drift:
none"* on both, with no other value changed, so the two shipped repairs are
confirmed clean by a check that did not exist when they were made.

**And formcheck cannot see it either.** On the unshipped `django-11179` repair,
`symbol_rename:Collector` goes from WITNESS to CLEAN with reward 1.0 on a
genuinely distinct tree. A repair can pass formcheck, pass C1, pass C2, and still
be strictly weaker than what it replaced. That is the same shape as every entry in
`CHANGES.md` §7's family: a check returning a verdict for a reason invisible in
its own output.

Evidence: `repair/M0D_RESULT.md`,
`repair/test_repair_m0d.py::test_the_repair_is_a_hollowing_out_that_c2_cannot_see`.

---

## Open item 1 — the attributable-to-one-import fraction across the 15

**The strongest second number available at €0 and with no inference. Not started.**

`REPORT.md` §3(a) reports that 15 of the 28 coupled tasks lose their entire
graded suite. `astropy-12907` shows the mechanism can be a single module-scope
import line, with 14 of its 15 failures collateral — but that is n = 1, and the
split is unmeasured on the other 14.

**The measurement.** For each of the 15 all-fail tasks, build the `import_local`
variant — move the renamed symbol's import out of module scope and into the test
functions that actually use it, changing nothing else — and grade it under the
rename. The fraction of failures that come back is the fraction attributable to
the import line rather than to tests that genuinely reference the symbol.

**Why it is worth doing.** It costs 15 container runs, uses the overlay surface
and the gate that already exist, involves no model and no judgement call, and it
answers the question the headline figure raises but cannot settle. It would turn
"the median coupled task loses 100% of its suite" from one number into two: how
much signal is destroyed, and how much of a suite is really coupled.

**What it is not.** It is not a repair, and it must not be reported as one: the
`import_local` variant still scores 0.0 on every task where any test genuinely
names the symbol. It is a decomposition of an existing number, and the honest
framing is that it makes the existing number *more* interpretable, not smaller.

**One thing to fix first.** The 15 include 8 django tasks, and django's runner
reports import failure as a synthetic `unittest.loader._FailedTest` with no real
node ids in the status map. Whether the variant is even measurable there is the
question `repair-M0d` exists to answer.
