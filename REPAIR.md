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

**Status: a hypothesis from n = 1. Not a rule, not yet a family.**

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

**Why it might not.** One case, one repo, one operator, one shape. Specifically:

* `xarray-4966` is the module-attribute shape (`AttributeError: module … has no
  attribute …`), which is **9 of the 28** tasks. The larger group — 19 of 28 — is
  `ImportError: cannot import name …`, and 10 of those die at *collection*: the
  test module does not import at all. There may be no test body to rewrite, and
  the entry-point/assertion distinction may not even apply.
* xarray had a public entry point that reaches the same behaviour with the same
  discriminating power. That is a property of the library, not of the coupling.
  A task whose behaviour is only reachable through an internal symbol cannot be
  repaired this way at all, and it is not yet known how common that is.
* The repaired test kept identical detection: every mutant's F2P breakdown was
  unchanged. Whether a public entry point *generally* preserves discrimination,
  or whether xarray's `decode_cf` happened to be a thin wrapper, is untested.

**What would confirm or kill it.** A second and third case in different repos and
different shapes. If the `from … import` shape repairs by the same move — change
what the test imports, leave the assertions alone — the pattern survives. If it
requires rewriting assertions, or cannot be repaired at all, the pattern is
xarray-specific and this section should say so.

Evidence: `repair/M0B_RESULT.md`, `repair/m0b_gate.py`,
`repair/test_repair_m0b.py`.

---

## Open question 1 — an operator that anchors on public re-exports

**Status: deliberately not done. Logged with the reasoning, not deferred
silently.**

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
