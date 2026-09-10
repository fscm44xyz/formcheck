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

