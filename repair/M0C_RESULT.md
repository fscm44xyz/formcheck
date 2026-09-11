# repair-M0c — `astropy__astropy-12907`, the import shape

The second repair target, picked before looking at how hard it would be.

## Per-repo counts across the 28 witness tasks

| repo | tasks | witness rows | shapes (tasks) |
|---|---|---|---|
| django/django | **14** | 18 | import 10, module-attr 4 |
| pytest-dev/pytest | 3 | 3 | import 1, module-attr 2 |
| sphinx-doc/sphinx | 3 | 4 | import 2, module-attr 1 |
| pylint-dev/pylint | 2 | 3 | import 1, module-attr 1 |
| scikit-learn/scikit-learn | 2 | 2 | import 2 |
| astropy/astropy | 1 | 1 | import 1 |
| psf/requests | 1 | 1 | import 1 |
| pydata/xarray | 1 | 1 | module-attr 1 |
| sympy/sympy | 1 | 1 | import 1 |
| **total** | **28** | **34** | |

Django is half the population and is excluded for now, as instructed — its
failures arrive as a synthetic `unittest.loader._FailedTest` with no real node
ids in the status map, so the positive control behaves differently there.

## The pick

Applying the criteria in order — import shape; not xarray; `p2p_coupling`;
single-file gold; not django — leaves five: `astropy-12907`,
`psf__requests-1766`, `scikit-learn-14141`, `scikit-learn-14983`,
`sphinx-7454`. The criteria are then exhausted, so the tiebreak is
**lexicographic instance id**, fixed before inspecting any of them, on the same
before-the-result discipline as `scale/STOPPING_RULE.md`.

**`astropy__astropy-12907`**, anchor `_cstack`, single-file one-line gold patch,
`p2p_coupling`, collection error, F2P 0/2 and P2P 0/13 — the whole suite lost.

## 1. Positive control

`repair/overlay_positive_astropy_12907.diff` inserts
`assert False, "overlay landed"` into `test_cstack` only.

```
control.passed : False
control.reason : ... scored 0.0, not 1.0; F2P 2/2, P2P 12/13;
                 first failing: astropy/.../test_separable.py::test_cstack
"overlay landed" verbatim in log : True   (1 occurrence)
node ids reported                : 15
failed                           : ['...::test_cstack']   -- exactly the target
all others                       : PASSED
```

The surface works on a second repo. Re-established rather than assumed.

## 2. What the coupled tests assert, versus how they reach the code

`astropy/modeling/tests/test_separable.py` has **6 test functions** and reaches
production code through **one module-level import**, lines 13–14:

```python
from astropy.modeling.separable import (_coord_matrix, is_separable, _cdot,
                                        _cstack, _arith_oper, separability_matrix)
```

`separable.py` declares `__all__ = ["is_separable", "separability_matrix"]`.
Four of the six imported names are `_`-private.

| test function | lines | reaches the code via |
|---|---|---|
| `test_coord_matrix` | 76–94 | `_coord_matrix` (private) |
| `test_cdot` | 97–112 | `_cdot` (private) |
| **`test_cstack`** | **115–130** | **`_cstack` (private, the anchor)** |
| `test_arith_oper` | 133–146 | `_arith_oper` (private) |
| `test_separable` *(F2P)* | 150–152 | `is_separable`, `separability_matrix` — **public** |
| `test_custom_model_separable` | 155–167 | `separability_matrix` — **public** |

**`_cstack` is used by exactly one test function**, at three call sites, all
inside `test_cstack` (lines 116, 119, 125). The only other occurrence in the file
is the import.

So the failure is at collection, and the arithmetic is stark: **one name in one
import statement takes down all 15 graded tests, and 14 of them never use it.**
Both FAIL_TO_PASS tests — the ones the issue is actually about — already reach
the code through public API and are pure collateral.

### The measurement that separates collateral from intrinsic

A third test variant, `import_local`, changes nothing except where `_cstack` is
imported: dropped from the module import, imported inside `test_cstack`. Under
the rename:

| variant | F2P | P2P | reward |
|---|---|---|---|
| `original` | 0/2 | 0/13 | 0.0 |
| `import_local` | **2/2** | **12/13** | 0.0 |
| `repaired` | 2/2 | 13/13 | **1.0** |

**14 of the 15 failures were the import line.** The 15th is `test_cstack`, whose
*subject* is the renamed symbol — no placement of the import can save it, because
a test that calls `_cstack` by name must fail when `_cstack` is renamed. That is
why `import_local` is a diagnostic and not a repair: it recovers the collateral
and still scores 0.0.

## Does the xarray pattern hold?

**Yes, and more cleanly than in xarray.** Candidate pattern 1 said the coupling
tends to live in how a test *reaches* the code, not in what it *asserts*. Here
the assertion expressions are not merely equivalent — they are **byte-identical
before and after**. Only the call changed:

```diff
 def test_cstack():
-    result = _cstack(sh1, scl1)
+    result = separability_matrix(sh1 & scl1)
     assert_allclose(result, np.array([[1, 0], [0, 1]]))
 
-    result = _cstack(sh1, rot)
+    result = separability_matrix(sh1 & rot)
     assert_allclose(result,
                     np.array([[1, 0, 0],
                               [0, 1, 1],
                               [0, 1, 1]])
                     )
-    result = _cstack(rot, sh1)
+    result = separability_matrix(rot & sh1)
```

plus dropping `_cstack` from the module import:

```diff
 from astropy.modeling.separable import (_coord_matrix, is_separable, _cdot,
-                                        _cstack, _arith_oper, separability_matrix)
+                                        _arith_oper, separability_matrix)
```

`_cstack` is the function behind the `&` operator, so `separability_matrix(a & b)`
reaches the same code. Verified numerically before writing the repair: for all
three cases the public result equals the private one as booleans, which is why
the expected matrices did not have to change.

**What is new relative to xarray**, and worth recording:

* The coupling was at **module scope**, so the blast radius (15) was 15× the
  number of coupled tests (1). In xarray the two coupled tests were the only ones
  affected, and 17 others kept running.
* The 15th failure is **intrinsic**: `test_cstack` is a unit test *of a private
  helper*. Repairing it means changing what it enters through, and that is a
  judgement, not a mechanical fix. It is defensible here only because
  `separability_matrix` demonstrably computes the same thing for these inputs.
* The node id `test_cstack` now names a function that no longer calls `_cstack`.
  It is kept because the grader requires it: a renamed node id is scored as a
  failure (`repair/CONTEXT.md` §3.3).

**Not repaired, and reported instead:** `_coord_matrix`, `_cdot` and
`_arith_oper` sit in the same import line with the identical latent coupling —
renaming any one of them would also take down all 15 tests. `formcheck` never
flagged them because the gold patch does not touch them, so they are out of
scope. Repairing them would be fixing what the harness did not find.

## 3. Both conditions

`~/.venv-fc/bin/python repair/m0c_gate.py`

```
astropy__astropy-12907  --  reward by (test variant x solution)

  solution                         original             import_local                 repaired   effect
  gold               1.0  F2P 2/2 P2P 13/13   1.0  F2P 2/2 P2P 13/13   1.0  F2P 2/2 P2P 13/13
  gold_renamed        0.0  F2P 0/2 P2P 0/13   0.0  F2P 2/2 P2P 12/13   1.0  F2P 2/2 P2P 13/13
  bug_revert         0.0  F2P 0/2 P2P 13/13   0.0  F2P 0/2 P2P 13/13   0.0  F2P 0/2 P2P 13/13   the pre-issue behaviour: the right block is filled with ones
  bug_leftblock      0.0  F2P 1/2 P2P 11/13   0.0  F2P 1/2 P2P 11/13   0.0  F2P 1/2 P2P 11/13   the mirror bug on the left operand's block
  bug_stackorder      0.0  F2P 0/2 P2P 6/13    0.0  F2P 0/2 P2P 6/13    0.0  F2P 0/2 P2P 6/13   operand columns emitted in the wrong order

  C1  renamed gold, repaired test  reward = 1.0  OK
      (original test: 0.0 -- the witness)

  C2  behavioural mutants, repaired test:
      bug_revert       reward = 0.0  CAUGHT   (original: 0.0  import_local: 0.0)
      bug_leftblock    reward = 0.0  CAUGHT   (original: 0.0  import_local: 0.0)
      bug_stackorder   reward = 0.0  CAUGHT   (original: 0.0  import_local: 0.0)

  G1  original gold, repaired test reward = 1.0  OK

  -> PASS
```

All three mutants are expression edits inside `_cstack`; no identifier, import or
class name is touched, and `names_symbol_in_log` is false for all **nine** mutant
runs. Detection is identical across all three test variants, mutant by mutant,
including the partial catches (`bug_leftblock` leaves F2P 1/2 and P2P 11/13 under
every variant) — so the repair removed nothing.

## 4. The 1.0 ran on a tree carrying the rename

```
repaired-run digest_trace:
  4e76563bf268e2f3d38551c4ad6daa7c566a7badadef69a9f5880df6e413a803  memo_hit=False   control
  53a020442fba2cb7128311e7966891f1644e8d941fdc436f51f872d699bda5bb  memo_hit=False   transformed
  53a020442fba2cb7128311e7966891f1644e8d941fdc436f51f872d699bda5bb  memo_hit=True    re-grade
```

Control and transformed digests differ, so the 1.0 was graded, not served from
the memo. The repaired-run control digest also differs from the un-overlaid run's
(`b9d6dacb…`), which is how the overlay is known to have landed.

## 5. formcheck re-run — and what it cannot prove

| case | before | after |
|---|---|---|
| `<control>` | OK | OK |
| **`symbol_rename:_cstack`** | **WITNESS** | **CLEAN** |
| the three no-anchor operators | NOT_APPLICABLE | NOT_APPLICABLE |

```
witnesses : none
detail    : {"new_name": "_cstack__renamed", "references_rewritten": 2,
             "files_changed": ["astropy/modeling/separable.py"], "files_scanned": 488}
graded    : reward 1.0, f2p 2/2, p2p 13/13, n_parsed 15
```

**The same limit as `decode_cf`, stated again because it has not gone away.**
`formcheck` offers anchors only from symbols the gold patch overlaps. This patch
changes one line inside `_cstack`, so `_cstack` is the sole anchor before and
after — **`separability_matrix`, the symbol the repair now depends on, is not
probed and cannot be.** A CLEAN here means "the anchor formcheck can offer no
longer produces a witness", not "no coupling remains".

That the coupling did not simply move rests on two checkable facts, neither of
which is a formcheck verdict:

1. `separability_matrix` is exported: `__all__ = ["is_separable",
   "separability_matrix"]` in `astropy/modeling/separable.py` line 24.
2. The repaired `test_cstack` names no private symbol at all — every added call
   goes through `separability_matrix`, and the module import no longer mentions
   `_cstack`.

Both are asserted in `repair/test_repair_m0c.py`. See `REPAIR.md`, open question 1.

## Artifacts

| | |
|---|---|
| `repair/overlay_repair_astropy_12907.diff` | the repair |
| `repair/overlay_importlocal_astropy_12907.diff` | the collateral/intrinsic diagnostic |
| `repair/overlay_positive_astropy_12907.diff` | the positive control |
| `repair/m0c_gate.py`, `repair/gate.py` | the gate (engine now shared with M0b) |
| `repair/m0c_gate_result.json` | the matrix above |
| `repair/records_m0c/{plain,positive,repaired}/` | the three harness runs |
| `repair/test_repair_m0c.py` | all of the above pinned offline |
