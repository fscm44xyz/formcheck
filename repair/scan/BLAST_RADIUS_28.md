# Blast radius of the boundary defect across the 28 witness tasks

Answers the question `189451b` left open and could not settle by reading the
records: on the 28 tasks that carry a `WITNESS` row, was the rename the
published 500-task run actually performed a well-formed alpha-rename?

**Result: all 34 witness rows across all 28 tasks stand. No row is void. No row
is undetermined.**

## What was compared

For each recorded witness row the task's production tree was rebuilt offline —
base commit + `tests.diff` + `gold.diff`, the tree `formcheck_read` saw — the
anchor re-derived from that tree, and `SymbolRename` applied twice:

| | |
|---|---|
| **OLD** | `repro/f2_operators.py` at `189451b` — the code that produced the run |
| **NEW** | `repro/f2_operators.py` at HEAD — both branches taking AST spans |

The recorded rename was well-formed if and only if the two agree byte for byte
on every file. This is a direct comparison of what the run's operator did
against what a correct one does. It does not go through the round-trip
invariant, which is a check on one operator's output rather than a comparison
between two.

## Why the result is believable

A measurement that puts every row in one bucket is worth nothing until the other
buckets are shown to be reachable, and until "the two agree" is shown to mean
something other than "neither did anything". Both were checked.

**The comparison can report `witness void`.** Two shapes the old operator
provably corrupts are pushed through the same `classify` the 34 rows go through,
as a positive control that runs before the table. Both come back void. If they
did not, the run aborts rather than printing a table.

**Every row rewrote real files** — 1, 2, 3, 5 and 11 files across the 34 — and a
row where both operators applied but changed nothing is bucketed undetermined,
not "stands".

**The rewrite compared is the rewrite that was recorded.** Applying OLD to the
rebuilt tree reproduces the `tree_digest` that row recorded, on **34 of 34
rows**. The trees are therefore byte-identical to the ones the run saw, and the
thing being held against the corrected operator is the recorded rewrite itself
rather than a reconstruction that resembles it. A row that failed this check
would have been moved to undetermined, because the comparison would then be
between something else and the corrected operator.

## Why nothing was hit

The defect needs the anchor to appear as a substring **earlier on the same
import line** — before the alias, or inside the module path. Across these 28
tasks no such line exists. The near miss is the shape that looks most dangerous
and is not: `class DatabaseClient(BaseDatabaseClient)` in three django tasks,
where the superstring is on the `class` line and reached through the `ClassDef`
branch, while the import line names only `BaseDatabaseClient` — an alias that is
not the anchor, so the `ImportFrom` branch never fires. That is probe case 4.

## The table

Per row, not per task: `django-13212` carries five anchors in one file and
`sphinx-7590` carries the same anchor in two.

```
task                             anchor                   file                                      recorded rename
astropy__astropy-12907           _cstack                  astropy/modeling/separable.py             witness stands
django__django-11179             Collector                django/db/models/deletion.py              witness stands
django__django-11433             construct_instance       django/forms/models.py                    witness stands
django__django-12155             parse_docstring          django/contrib/admindocs/utils.py         witness stands
django__django-13121             Combinable               django/db/models/expressions.py           witness stands
django__django-13195             CookieStorage            django/contrib/messages/storage/cookie.py witness stands
django__django-13212             RegexValidator           django/core/validators.py                 witness stands
django__django-13212             URLValidator             django/core/validators.py                 witness stands
django__django-13212             validate_ipv4_address    django/core/validators.py                 witness stands
django__django-13212             validate_ipv6_address    django/core/validators.py                 witness stands
django__django-13212             validate_ipv46_address   django/core/validators.py                 witness stands
django__django-14311             get_child_arguments      django/utils/autoreload.py                witness stands
django__django-14315             DatabaseClient           django/db/backends/postgresql/client.py   witness stands
django__django-14376             DatabaseClient           django/db/backends/mysql/client.py        witness stands
django__django-14771             get_child_arguments      django/utils/autoreload.py                witness stands
django__django-15380             MigrationAutodetector    django/db/migrations/autodetector.py      witness stands
django__django-15572             get_template_directories django/template/autoreload.py             witness stands
django__django-15851             DatabaseClient           django/db/backends/postgresql/client.py   witness stands
django__django-15973             MigrationAutodetector    django/db/migrations/autodetector.py      witness stands
psf__requests-1766               HTTPDigestAuth           requests/auth.py                          witness stands
pydata__xarray-4966              UnsignedIntegerCoder     xarray/coding/variables.py                witness stands
pylint-dev__pylint-4551          get_annotation           pylint/pyreverse/utils.py                 witness stands
pylint-dev__pylint-4551          infer_node               pylint/pyreverse/utils.py                 witness stands
pylint-dev__pylint-4604          VariablesChecker         pylint/checkers/variables.py              witness stands
pytest-dev__pytest-10356         get_unpacked_marks       src/_pytest/mark/structures.py            witness stands
pytest-dev__pytest-5809          create_new_paste         src/_pytest/pastebin.py                   witness stands
pytest-dev__pytest-7521          FDCaptureBinary          src/_pytest/capture.py                    witness stands
scikit-learn__scikit-learn-14141 _get_deps_info           sklearn/utils/_show_versions.py           witness stands
scikit-learn__scikit-learn-14983 _build_repr              sklearn/model_selection/_split.py         witness stands
sphinx-doc__sphinx-7454          _parse_annotation        sphinx/domains/python.py                  witness stands
sphinx-doc__sphinx-7590          DefinitionParser         sphinx/domains/c.py                       witness stands
sphinx-doc__sphinx-7590          DefinitionParser         sphinx/domains/cpp.py                     witness stands
sphinx-doc__sphinx-7757          signature_from_str       sphinx/util/inspect.py                    witness stands
sympy__sympy-13031               MutableSparseMatrix      sympy/matrices/sparse.py                  witness stands

recorded rewrite reproduced from the rebuilt tree: 34 of 34 rows

witness stands   rows 34   tasks 28
witness void     rows  0   tasks  0
undetermined     rows  0   tasks  0
```

## What this does and does not settle

**Settles.** No published witness rests on a rewrite that landed inside a longer
identifier. The defect was real, it was reachable, and on these 28 tasks it was
not reached.

**Does not settle.** Nothing about the 466 non-witness tasks. A task whose row
came back `CLEAN`, `REFUSED` or `NOT_APPLICABLE` is outside this scan, and a
corrupted rewrite there would have pushed a row away from `WITNESS`, not toward
it — the direction that biases the count downward and that nobody audits.
Measuring it is a different scan with a different denominator.

No corrected rate is derived here and nothing in `REPORT.md` changes: 34 rows
over 28 tasks is not the denominator any published number uses, and what the
number should now mean is a separate decision.

## Reproducing

```bash
FORMCHECK_REPO_CACHE=<dir> ~/.venv-fc/bin/python repair/scan/blast_radius_28.py
```

Needs network for the clones. No Docker, no model, no judgement call. Results in
`repair/scan/BLAST_RADIUS_28.json`, one entry per row including whether that
row's recorded digest was reproduced.
