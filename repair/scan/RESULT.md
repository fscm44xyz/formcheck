# Does the benchmark's test patch introduce the coupled reference?

Static scan, no Docker, no model, no inference beyond reading unified diffs.
`repair/scan/test_patch_origin.py`, reproducible in about ten seconds:

```bash
~/.venv-fc/bin/python repair/scan/test_patch_origin.py
```

For each witness (task, coupled symbol), where the test tree's reference to that
symbol comes from:

| class | meaning |
|---|---|
| `introduced` | the symbol appears on a `+` line of the task's `test_patch`, in a file that already existed |
| `mixed` | the symbol appears on both `+` lines and unchanged context lines — the patch added references to a symbol the tests already used |
| `pre_existing` | the symbol appears in the `test_patch` only on context/`-` lines, or not at all |
| `new_file` | the symbol appears on a `+` line in a file the patch **creates** — counted separately, never folded in |

`pre_existing` is asserted rather than assumed: a graded test that fails under the
rename must reference the symbol somewhere, so if the patch never adds it, the
reference was already in the repository's test tree. Every `pre_existing` row
below is the strongest form — the symbol appears **nowhere** in the test patch
(`+/ctx = 0/0`).

**No conclusion is drawn here and nothing from this scan has been written into
`REPORT.md`.**

## The raw table

34 witness (task, symbol) pairs across 28 tasks. `+/ctx` counts lines
referencing the symbol on the added and context sides.

| task | symbol | origin | where the added reference sits | +/ctx |
|---|---|---|---|---|
| `astropy__astropy-12907` | `_cstack` | **pre_existing** | — | 0/0 |
| `django__django-11179` | `Collector` | **introduced** | in_test, module_import | 2/0 |
| `django__django-11433` | `construct_instance` | **pre_existing** | — | 0/0 |
| `django__django-12155` | `parse_docstring` | **mixed** | in_test, module_import | 2/2 |
| `django__django-13121` | `Combinable` | **pre_existing** | — | 0/0 |
| `django__django-13195` | `CookieStorage` | **pre_existing** | — | 0/0 |
| `django__django-13212` | `RegexValidator` | **introduced** | in_test | 1/0 |
| `django__django-13212` | `URLValidator` | **introduced** | in_test | 5/0 |
| `django__django-13212` | `validate_ipv4_address` | **introduced** | in_test | 1/0 |
| `django__django-13212` | `validate_ipv6_address` | **introduced** | in_test | 1/0 |
| `django__django-13212` | `validate_ipv46_address` | **introduced** | in_test | 1/0 |
| `django__django-14311` | `get_child_arguments` | **introduced** | in_test | 1/0 |
| `django__django-14315` | `DatabaseClient` | **pre_existing** | — | 0/0 |
| `django__django-14376` | `DatabaseClient` | **pre_existing** | — | 0/0 |
| `django__django-14771` | `get_child_arguments` | **mixed** | in_test | 1/4 |
| `django__django-15380` | `MigrationAutodetector` | **pre_existing** | — | 0/0 |
| `django__django-15572` | `get_template_directories` | **introduced** | in_test | 1/0 |
| `django__django-15851` | `DatabaseClient` | **pre_existing** | — | 0/0 |
| `django__django-15973` | `MigrationAutodetector` | **pre_existing** | — | 0/0 |
| `psf__requests-1766` | `HTTPDigestAuth` | **introduced** | in_test | 1/0 |
| `pydata__xarray-4966` | `UnsignedIntegerCoder` | **introduced** | in_test | 2/0 |
| `pylint-dev__pylint-4551` | `get_annotation` | **introduced** | in_test, module_import | 5/0 |
| `pylint-dev__pylint-4551` | `infer_node` | **introduced** | in_test, module_import | 3/0 |
| `pylint-dev__pylint-4604` | `VariablesChecker` | **pre_existing** | — | 0/0 |
| `pytest-dev__pytest-10356` | `get_unpacked_marks` | **introduced** | in_test, local_import | 3/0 |
| `pytest-dev__pytest-5809` | `create_new_paste` | **pre_existing** | — | 0/0 |
| `pytest-dev__pytest-7521` | `FDCaptureBinary` | **pre_existing** | — | 0/0 |
| `scikit-learn__scikit-learn-14141` | `_get_deps_info` | **pre_existing** | — | 0/0 |
| `scikit-learn__scikit-learn-14983` | `_build_repr` | **pre_existing** | — | 0/0 |
| `sphinx-doc__sphinx-7454` | `_parse_annotation` | **mixed** | in_test | 1/2 |
| `sphinx-doc__sphinx-7590` | `DefinitionParser` | **pre_existing** | — | 0/0 |
| `sphinx-doc__sphinx-7590` | `DefinitionParser` | **pre_existing** | — | 0/0 |
| `sphinx-doc__sphinx-7757` | `signature_from_str` | **mixed** | in_test | 1/1 |
| `sympy__sympy-13031` | `MutableSparseMatrix` | **pre_existing** | — | 0/0 |

## Counts

Two denominators, because three tasks carry more than one witness symbol
(`django-13212` has five, `pylint-4551` and `sphinx-7590` two each — six extra
pairs, which is why 34 pairs span 28 tasks).

| class | (task, symbol) pairs of 34 | tasks of 28 |
|---|---|---|
| `introduced` | 13 | 8 |
| `mixed` | 4 | 4 |
| `pre_existing` | 17 | 16 |
| `new_file` | 0 | 0 |

A task counts as `introduced` if any of its symbols is, and `mixed` if any is
mixed — so the task column is the generous reading for "the benchmark touched
it".

**`new_file` is 0.** No witness symbol arrives in a file the test patch creates,
so the ambiguous bucket the scan was designed to isolate turns out to be empty
and nothing is being folded in.

Read together: the benchmark's test patch adds at least one reference to the
coupled symbol in **12 of 28** tasks, and
in the other **16** the reference is already in the
repository's test tree, untouched by the patch.

## Where the added reference sits

Of the 17 introduced/mixed pairs:

| location | pairs |
|---|---|
| in_test | 12 |
| in_test, module_import | 4 |
| in_test, local_import | 1 |

The `django-11179` shape — the benchmark adding a **module-scope import**, which
is what couples an entire test module to one name — is 4 pairs across
3 tasks:

* `django__django-11179` — `Collector` (introduced)
* `django__django-12155` — `parse_docstring` (mixed)
* `pylint-dev__pylint-4551` — `get_annotation` (introduced)
* `pylint-dev__pylint-4551` — `infer_node` (introduced)

Everything else the benchmark adds is an in-test reference: a call, an
attribute, an argument inside a test body.

## By repository


| repo | tasks | introduced | mixed | pre_existing |
|---|---|---|---|---|
| django/django | 14 | 4 | 2 | 8 |
| pytest-dev/pytest | 3 | 1 | 0 | 2 |
| sphinx-doc/sphinx | 3 | 0 | 2 | 1 |
| pylint-dev/pylint | 2 | 1 | 0 | 1 |
| scikit-learn/scikit-learn | 2 | 0 | 0 | 2 |
| astropy/astropy | 1 | 0 | 0 | 1 |
| psf/requests | 1 | 1 | 0 | 0 |
| pydata/xarray | 1 | 1 | 0 | 0 |
| sympy/sympy | 1 | 0 | 0 | 1 |

## One correction this scan forced

An earlier note in `REPAIR.md` (candidate pattern 2) said that on *both*
`astropy-12907` and `django-11179` the coupling was introduced by the benchmark's
own test patch. **That is wrong for astropy.** `astropy-12907`'s test patch adds
`cm_4d_expected` and four `compound_models` entries and never mentions `_cstack`;
the coupling import at `test_separable.py:13-14` pre-exists in the repository.
The claim held for `django-11179` and was generalised from one case to two
without checking the second. It has been corrected.


---

# On the 15 all-fail tasks, did any graded test run?

Static. No Docker. `repair/scan/allfail_mechanism.py`, reading the `graded_log`
already recorded by the 500-task run plus the dataset's own F2P/P2P lists.

**This is not the `import_local` measurement.** That one needs 15 container runs —
`REPAIR.md` §9 says so — and has not been run. This answers the half of the
question the recorded logs already settle, and it costs nothing.

For each all-fail witness, how many of the task's graded node ids the runner
actually reported under the rename:

| task | symbol | node ids reported | graded | mechanism |
|---|---|---|---|---|
| `astropy__astropy-12907` | `_cstack` | 0 | 15 | ran_none |
| `django__django-11179` | `Collector` | 0 | 41 | ran_none |
| `django__django-11433` | `construct_instance` | 0 | 143 | ran_none |
| `django__django-12155` | `parse_docstring` | 0 | 7 | ran_none |
| `django__django-14376` | `DatabaseClient` | 0 | 9 | ran_none |
| `django__django-15380` | `MigrationAutodetector` | 0 | 134 | ran_none |
| `django__django-15851` | `DatabaseClient` | 0 | 9 | ran_none |
| `django__django-15973` | `MigrationAutodetector` | 0 | 158 | ran_none |
| `psf__requests-1766` | `HTTPDigestAuth` | 0 | 85 | ran_none |
| `pylint-dev__pylint-4551` | `get_annotation` | 0 | 10 | ran_none |
| `pylint-dev__pylint-4551` | `infer_node` | 0 | 10 | ran_none |
| `pylint-dev__pylint-4604` | `VariablesChecker` | 0 | 21 | ran_none |
| `scikit-learn__scikit-learn-14141` | `_get_deps_info` | 0 | 3 | ran_none |
| `scikit-learn__scikit-learn-14983` | `_build_repr` | 0 | 107 | ran_none |
| `sphinx-doc__sphinx-7454` | `_parse_annotation` | 0 | 28 | ran_none |
| `sphinx-doc__sphinx-7590` | `DefinitionParser` | 0 | 25 | ran_none |
| `sphinx-doc__sphinx-7590` | `DefinitionParser` | 0 | 25 | ran_none |

17 witness rows across 15 tasks (`pylint-4551` and `sphinx-7590` each carry two
witness symbols over the same suite; the totals below deduplicate by task).

## Aggregate

```
ran_none : 15 of 15 tasks -- 795 graded tests across them, none executed
ran_some :  0 of 15 tasks
```

**On every one of the 15, the runner reported zero graded node ids.** Not one of
the 795 tests executed. Every one of the 795 failures is scored by
`test_failed`'s `case not in sm` branch — absence, not a test that ran and failed.

## What this does and does not establish

It establishes the **mechanism** on all 15: the total suite loss is a
module-import failure in every case, across four repos and both test runners.
None of these tasks is one where each test independently references the symbol
and fails on its own terms — there are zero such tasks among the 15.

It does **not** give the fraction. How many of the 795 would recover if the
import were moved off module scope is `N − k` per task, where `k` is the number
of tests that name the symbol themselves, and `k` is not derivable from a log
that shows nothing running. `k = 1` on the three tasks where `import_local` has
actually been run (`astropy-12907`, `django-11179`, `django-11433` — 14/15, 40/41,
142/143), which is a measurement on 3 of 15, not an assumption about the other 12.

So the honest bound is: on all 15 the 100% is an import failure rather than
per-test coupling, and on 3 of 15 the residual is exactly one test. The remaining
12 need the container runs.

## One thing to note about this scan

`psf__requests-1766`'s row went missing from two earlier terminal readings of
these scans. The cause was a `grep -v "HTTP"` filter used to strip HTTP request
logging from the output: its symbol is `HTTPDigestAuth`. The data was never
affected — both scans wrote JSON — but the displayed table was, twice, and the
row was noticed missing by counting rather than by reading. The scans now write
their JSON unconditionally so the file rather than the terminal is the artifact.

The artifact for this scan is `repair/scan/test_patch_origin.json`, one row per
task, written by `test_patch_origin.py --json`. The remaining 12 tasks' container
runs referred to above were done, and are reported in
`repair/scan/IMPORT_LOCAL_RESULT.md`.
