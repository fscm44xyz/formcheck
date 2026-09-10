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

**Status: held on n = 2, in two repos and both failure shapes. Two cases are not
a family either — but it has now survived the case chosen to break it.**

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

**What is still not established.** Both repaired tasks happened to have a public
entry point reaching the same behaviour with the same discriminating power. That
is a property of the library, not of the coupling. A task whose behaviour is only
reachable through an internal symbol cannot be repaired this way at all, and how
common that is remains unmeasured. The remaining caveats:

* **django is half the corpus and untested.** 14 of the 28 witness tasks are
  django, excluded so far because their failures arrive as a synthetic
  `unittest.loader._FailedTest` with no real node ids in the status map. Nothing
  here has been shown to apply to them.
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

**Status: measured once, on `astropy__astropy-12907`. n = 1.**

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

If this holds elsewhere, the headline number's *blast radius* figure — "in 15 of
28 tasks every graded test fails" (`README.md`) — is largely a statement about
module-level imports rather than about how much of a suite is really coupled.
That would be worth knowing and is not yet known: it needs the same
`import_local` measurement on more of the 19 import-shape tasks.

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

## The two conditions any repair must pass

Established in `repair-M0b` and expected to hold for every case:

| | |
|---|---|
| **C1** | the renamed gold scores **1.0** — the coupling is gone |
| **C2** | genuinely broken solutions still score **0.0** — the test was not hollowed out |

Neither is sufficient. A test asserting nothing passes C1 and fails C2; the
original coupled test passes C2 and fails C1.

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
