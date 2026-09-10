# `import_local` across the 12 — complete

`REPAIR.md` §9 open item 1: on each all-fail task, move the coupled symbol's
module-scope import into the test functions that use it, re-grade under the same
rename, and report how much of the suite loss is attributable to that one line.

**All 12 tasks measured. 13 unique (task, symbol) measurements.**

    N          graded tests
    k          still failing after the import is moved -- the tests that reach the symbol
    recovery   N - k, attributable to the single module-scope import line

## The table

```
task                               symbol                     N     k  recovery  outcome
scikit-learn__scikit-learn-14983   _build_repr              107     1       106  measured
sphinx-doc__sphinx-7454            _parse_annotation         28     1        27  measured
django__django-15380               MigrationAutodetector    134   122        12  measured
django__django-15973               MigrationAutodetector    158   146        12  measured
sphinx-doc__sphinx-7590            DefinitionParser          25    16         9  measured
pylint-dev__pylint-4551            infer_node                10     2         8  measured
pylint-dev__pylint-4551            get_annotation            10     4         6  measured
django__django-12155               parse_docstring            7     4         3  measured
scikit-learn__scikit-learn-14141   _get_deps_info             3     1         2  measured
django__django-14376               DatabaseClient             9     9         0  helper_coupled
django__django-15851               DatabaseClient             9     9         0  helper_coupled
psf__requests-1766                 HTTPDigestAuth             -     -         -  not_applicable
pylint-dev__pylint-4604            VariablesChecker           -     -         -  not_applicable

measured        9   (k = 1: 3,   k > 1: 6)
helper_coupled  2
not_applicable  2
```

`not_applicable` is not a recovery of zero. `requests-1766`: no test file
references the symbol. `pylint-4604`: no module-scope `from … import
VariablesChecker` to move — the shape §9 already predicted.

## The aggregate, and what selecting on `k = 1` does to it

**Over the `k = 1` rows only: 135 of 138 graded tests recovered, 97.8%.**

**Denominator: 3 rows.** Three of the nine measured, three of the thirteen
measurements, across twelve tasks.

That number should be read for what it is. Selecting `k = 1` *fixes* `recovery =
N − 1`, so the ratio is high by construction and the only real content in 97.8%
is that the three `N` values happen to be large. The aggregate does not say the
median coupled task recovers 97.8% of its suite. It says: on the three tasks
where exactly one test reaches the symbol, everything else came back.

## What the 12 do to the n = 3 mechanism

`REPAIR.md` §4 establishes, at n = 3, that one module-scope import takes down the
entire module and the single residual is the test whose *subject* is the symbol —
`k = 1` in all three. **That shape holds on 3 of the 9 measured here.** It is not
the distribution; it is one shape among several, and it was the first three seen.

The other six are `k > 1` and are listed rather than averaged:

```
django__django-15380     MigrationAutodetector   N=134   k=122   recovery=12
django__django-15973     MigrationAutodetector   N=158   k=146   recovery=12
sphinx-doc__sphinx-7590  DefinitionParser        N=25    k=16    recovery=9
pylint-dev__pylint-4551  infer_node              N=10    k=2     recovery=8
pylint-dev__pylint-4551  get_annotation          N=10    k=4     recovery=6
django__django-12155     parse_docstring         N=7     k=4     recovery=3
```

The two `MigrationAutodetector` tasks invert the picture the mechanism describes:
122 of 134 and 146 of 158 graded tests still fail once the import is moved, so
almost the whole suite genuinely reaches the symbol and only ~9% of the loss is
attributable to the import line. On those two, "the suite is destroyed by one
import" is false, and the reward damage and the coupling extent nearly coincide.

## `HELPER_COUPLED`, and why it is a verdict here

`django-14376` and `django-15851` both come back `recovery = 0` with the control
reproduced. That is a classification, not an abort, and it is decided by four
checks in code rather than by reading the row:

1. the round trip held on every renamed file
2. the residue grep is empty
3. the module loaded — graded node ids reported > 0
4. every graded test's own failure block names the symbol

Both tasks pass all four. Every graded test reaches `DatabaseClient` through one
shared helper — `settings_to_cmd_args_env`, called by eight of the nine, with the
ninth reaching it directly — so moving the import into the helper defers the
`ImportError` from load time to call time and removes nothing. The helper is the
coupling, not the import. No placement of that import can change these.

Check 3 is what separates this from the defect that voided the first run, where
`str.replace` broke the module and nothing ran at all
(`import_local_run.VOID.json`, `CHANGES.md` 34). `repair/scan/test_classify_zero.py`
pins both directions against the real log: the positive classifies, and each of
the four checks broken on its own aborts.

## Still not a repair

`import_local` scores **0.0 on every task here**, exactly as `REPAIR.md` §9 says.
It is a diagnostic that separates reward damage from coupling extent. It is not a
repair and must not be reported as one.

## Artifacts

`repair/scan/import_local_run.json` — 13 rows, written per row, unconditionally.
`repair/scan/import_local_run.VOID.json` — the first run, void, kept as the record
of the substitution defect biting.
