# repair-M0b — the repair of `pydata__xarray-4966`

The witness of `REPORT.md` was: rename `UnsignedIntegerCoder`, a behaviour-
preserving alpha-rename, and the task's reward drops to 0.0 — eight graded tests
fail with `AttributeError: module 'xarray.coding.variables' has no attribute
'UnsignedIntegerCoder'`. The reward was rejecting a correct solution for its
form.

This repairs the test so the reward stops doing that, and shows the repaired test
still rejects wrong programs.

## Scope: both call sites had to move, not four assertions

The brief named the four `test_decode_signed_from_unsigned` (FAIL_TO_PASS).
Repairing only those cannot satisfy condition 1: the identical coupling is in
`test_decode_unsigned_from_signed` (PASS_TO_PASS, line 130), and
`get_resolution_status` returns `FULL` only when F2P **and** P2P are green — so
`p2p_fail = 4` would have held the reward at 0.0. Both call sites are repaired.
Condition 1 is what forces it.

## The diff

`repair/overlay_repair_xarray_4966.diff`, generated from the real post-patch file
inside the image:

```diff
--- a/xarray/tests/test_coding.py
+++ b/xarray/tests/test_coding.py
@@ -127,8 +127,7 @@
     encoded = xr.Variable(
         ("x",), original_values.astype(signed_dtype), attrs={"_Unsigned": "true"}
     )
-    coder = variables.UnsignedIntegerCoder()
-    decoded = coder.decode(encoded)
+    decoded = xr.decode_cf(xr.Dataset({"v": encoded}))["v"]
     assert decoded.dtype == unsigned_dtype
     assert decoded.values == original_values
 
@@ -141,7 +140,6 @@
     encoded = xr.Variable(
         ("x",), original_values.astype(unsigned_dtype), attrs={"_Unsigned": "false"}
     )
-    coder = variables.UnsignedIntegerCoder()
-    decoded = coder.decode(encoded)
+    decoded = xr.decode_cf(xr.Dataset({"v": encoded}))["v"]
     assert decoded.dtype == signed_dtype
     assert decoded.values == original_values
```

The `assert` lines are untouched, because they were never the problem — they
already assert the issue's contract (`_Unsigned` decoding produces the right
dtype and the right values). What was coupled is the **entry point**: the test
reached the behaviour by constructing an internal class by name. It now reaches
the same behaviour through `xr.decode_cf`, which is exported in
`xarray/__init__.py`'s `__all__` (line 55).

Node ids are unchanged — same function names, same `parametrize` ids — which the
grader requires: `test_failed` counts a node id absent from the log as a
**failure**, so a renamed test pins the reward at 0.0 (`repair/CONTEXT.md` §3.3).

After the repair, `UnsignedIntegerCoder` occurs **0 times** in
`xarray/tests/test_coding.py`.

## Condition 1 — the renamed gold now scores 1.0

`~/.venv-fc/bin/python scale/run.py --instance-id pydata__xarray-4966
--tests-overlay repair/overlay_repair_xarray_4966.diff`

| case | before repair | after repair |
|---|---|---|
| `<control>` | OK | OK |
| `kwonly_specialize:<no anchor>` | NOT_APPLICABLE | NOT_APPLICABLE |
| **`symbol_rename:UnsignedIntegerCoder`** | **WITNESS** | **CLEAN** |
| `collection_reverse:<no anchor>` | NOT_APPLICABLE | NOT_APPLICABLE |
| `message_reword:<no anchor>` | NOT_APPLICABLE | NOT_APPLICABLE |

```
symbol_rename row AFTER : CLEAN | reward 1.0
graded_report           : reward 1.0, f2p 4/4, p2p 21/21, n_parsed 25
detail                  : {"new_name": "UnsignedIntegerCoder__renamed",
                           "references_rewritten": 3}
witnesses               : none
```

**Not a D2 false CLEAN.** The control tree and the transformed tree hash
differently — `34687e25…` vs `2f512d1a…` — so the 1.0 was produced by grading a
tree that really carries the rename, not by the memo returning the control's
result. That distinction is only visible because `digest_trace` records it, and
only correct because M0a item 1 made the digest cover the test files too.

## Condition 2 — a genuinely broken solution still scores 0.0

`~/.venv-fc/bin/python repair/m0b_gate.py`

Three mutants, each an expression edit inside the gold's own added branch. **No
identifier, import or class name is touched** — a mutant that broke the import
would fail the repaired test for the same coupled reason as before and would
prove nothing about behaviour.

```
pydata__xarray-4966  --  reward by (test variant x solution)

  solution                       original               repaired   effect
  gold             1.0  F2P 4/4 P2P 21/21 1.0  F2P 4/4 P2P 21/21
  gold_renamed     0.0  F2P 0/4 P2P 17/21 1.0  F2P 4/4 P2P 21/21
  bug_noop         0.0  F2P 0/4 P2P 21/21 0.0  F2P 0/4 P2P 21/21   the signed view is computed and then never applied
  bug_width        0.0  F2P 1/4 P2P 21/21 0.0  F2P 1/4 P2P 21/21   converts to int8 regardless of width -- correct only at bits=1
  bug_condflip     0.0  F2P 0/4 P2P 21/21 0.0  F2P 0/4 P2P 21/21   the added branch never fires for the case the issue describes

  C1  renamed gold, repaired test  reward = 1.0  OK
      (was 0.0 on the original test -- the witness)

  C2  behavioural mutants, repaired test:
      bug_noop       reward = 0.0  CAUGHT   (original test: 0.0)
      bug_width      reward = 0.0  CAUGHT   (original test: 0.0)
      bug_condflip   reward = 0.0  CAUGHT   (original test: 0.0)

  G1  original gold, repaired test reward = 1.0  OK

  -> PASS
```

The matrix is run for **both** test variants on purpose: "the repair did not
weaken detection" is a comparison, not an absolute. Every mutant's F2P breakdown
is **identical** under the original and the repaired test — including
`bug_width`, where both let `bits=1` through and catch the other three. The
repaired test detects exactly what the original detected, and one thing fewer
that it should never have detected: the rename.

The gate also asserts that no mutant's failure names the symbol
(`names_symbol_in_log` is `false` for all six mutant runs). A mutant whose
failure said `has no attribute 'UnsignedIntegerCoder'` would be coupled, not
behavioural, and the gate fails on it.

Grading is `repro/m4_grader.grade_log` — the same offline SWE-bench-format grader
the 500-task run used, over the same F2P/P2P lists. Nothing here is read off
pytest output by eye.

## Did the coupling just move?

**No witness on the anchor formcheck can offer.** The formcheck re-run above is
the direct evidence: `symbol_rename:UnsignedIntegerCoder` is now CLEAN and the
record carries no witnesses at all.

**Stated plainly: formcheck cannot probe the new entry point.** Anchors are
restricted to symbols the gold patch touches (`writeup.md` §3.3,
`scale/SCOPE.md`), and this gold patch touches only
`UnsignedIntegerCoder.decode`. `symbols_covering` yields `{UnsignedIntegerCoder,
decode}`, and `SymbolRename.anchors` walks module-level definitions only, so
`UnsignedIntegerCoder` is the sole anchor — before and after. `decode_cf` lives in
`xarray/conventions.py` and is re-exported from `xarray/__init__.py`; the rule
that would have to widen to reach it is the rule that exists precisely so anchors
cannot be chosen in view of the outcome. Widening it here would be selecting for
the result.

So the claim "the coupling did not move" rests on two things, and neither is a
formcheck verdict:

1. `xr.decode_cf` is public API — `"decode_cf"` is in `xarray/__init__.py`'s
   `__all__` at line 55. Coupling to an exported name is not the failure this
   project measures; the thesis is about *internal* symbols.
2. The repaired test names no module-internal symbol at all in either function:
   zero occurrences of `UnsignedIntegerCoder`, and no other `variables.*`
   reference in the two repaired bodies.

## Artifacts

| | |
|---|---|
| `repair/overlay_repair_xarray_4966.diff` | the repair |
| `repair/m0b_gate.py` | the two-condition gate, self-contained |
| `repair/m0b_gate_result.json` | the matrix above |
| `repair/records_m0a/repaired/` | the formcheck re-run record |
| `repair/test_repair_m0b.py` | both conditions pinned offline |
