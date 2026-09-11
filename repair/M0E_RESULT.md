# repair-M0e — `django__django-11433`, and the answer for the django stratum

Second django task, picked under the criterion fixed before `repair-M0d`: the
`from … import` shape, single-file gold patch, then lexicographic instance id.
Django witness tasks meeting the first two are `11179`, `11433`, `15380`,
`15851`, `15973`; `11179` was M0d, so this is **`django__django-11433`**, anchor
`construct_instance`.

**Outcome: HOLLOWING-OUT. C1 and C2 pass, C3 fails. Not shipped.**

## 1. Positive control

`repair/overlay_positive_django_11433.diff` inserts `assert False, "overlay
landed"` into `test_blank_with_null_foreign_key_field` only.

```
control.passed : False          n_parsed: 144
graded         : reward 0.0, f2p 1/1, p2p 141/142
p2p_failing    : ['test_blank_with_null_foreign_key_field (model_forms.tests.ModelFormBaseTest)']
"AssertionError: overlay landed" in graded_log : True
```

Exactly the targeted node id fails, by its own message. Second django task, same
result as M0d: the runner is not an obstacle.

## 2. What the coupled test asserts, versus how it reaches the code

`tests/model_forms/tests.py` has **144 test methods**, 143 of them graded.
`construct_instance` is named **three** times in the whole test tree, all in this
file:

```
 15: from django.forms.models import (                      <- module scope
        ModelFormMetaclass, construct_instance, fields_for_model, model_to_dict,
205:     "...if construct_instance receives fields=()."      <- a docstring
209:     instance = construct_instance(form, Person(), fields=())   <- one test
```

**One** of 144 test methods uses it. The coupled test is a PASS_TO_PASS test —
not the F2P test — and it is a unit test of the internal function:

```python
def test_empty_fields_to_construct_instance(self):
    """No fields should be set on a model instance if construct_instance receives fields=()."""
    form = modelform_factory(Person, fields="__all__")({'name': 'John Doe'})
    self.assertTrue(form.is_valid())
    instance = construct_instance(form, Person(), fields=())
    self.assertEqual(instance.name, '')
```

The single FAIL_TO_PASS test —
`test_default_not_populated_on_non_empty_value_in_cleaned_data`, added by the
task's test patch — uses only `forms.ModelForm` and `save(commit=False)`. It is
pure collateral, as are the other 141.

`construct_instance` is **not public**: absent from `django/forms/models.py`'s
`__all__` (`'ModelForm', 'BaseModelForm', 'model_to_dict', 'fields_for_model',
'ModelChoiceField', …`) and not re-exported from `django.forms`.

This task is `pre_existing` in the scan (`repair/scan/RESULT.md`) — the test
patch never mentions the symbol. The coupling is the repository's own.

## 3. The three-variant split

| variant, under the rename | F2P | P2P | reward |
|---|---|---|---|
| shipped test module | 0/1 | 0/142 | 0.0 |
| `import_local` | 1/1 | **141/142** | 0.0 |
| `repaired` | 1/1 | 142/142 | 1.0 |

**142 of 143 failures were the module-scope import line.** Candidate pattern 2
now holds at **n = 3**: astropy 14/15, django-11179 40/41, django-11433 142/143.

## 4. Classification, stated before the repair was proposed

Against the three outcome classes:

* **Not pattern 1.** Pattern 1 substitutes a public route for an internal one.
  The only public route to `construct_instance` is `ModelForm._post_clean`, which
  passes `opts.fields` from `Meta`. Reaching `fields=()` that way means a form
  declaring `fields = ()` — and **measured inside the image, before writing
  anything**:

  ```
  PROBE all_fields   valid: True  cleaned: {'name': 'John Doe'}
  PROBE construct_instance(fields=()) -> name=''
  PROBE empty_fields valid: True  n_fields: 0  cleaned: {}
  PROBE public save(commit=False)     -> name=''
  ```

  The public route reaches the same **assertion** by a different **mechanism**.
  In the coupled test `cleaned_data` holds `name`, and the `fields=()` filter
  inside `construct_instance` is what suppresses it. Through the public route
  `cleaned_data` is *empty*, so the filter never runs and the field is skipped one
  branch earlier. Same value, different code under test.

* **Not PRECONDITION.** The coupled line is the subject of the test, not a
  path-pinning assertion, and removing it removes the test's content rather than
  its scope.

* **HOLLOWING-OUT — predicted, then measured.** Because the public route bypasses
  the filter, a mutant that breaks the filter should stop being caught. The
  mutant `bug_fieldfilter` inverts exactly that line. C3 adjudicated.

## 5. Both conditions, and the third

```
django__django-11433  --  reward by (test variant x solution)

  solution                         original             import_local                 repaired   effect
  gold             1.0  F2P 1/1 P2P 142/142 1.0  F2P 1/1 P2P 142/142 1.0  F2P 1/1 P2P 142/142
  gold_renamed       0.0  F2P 0/1 P2P 0/142 0.0  F2P 1/1 P2P 141/142 1.0  F2P 1/1 P2P 142/142
  bug_revert       0.0  F2P 0/1 P2P 142/142 0.0  F2P 0/1 P2P 142/142 0.0  F2P 0/1 P2P 142/142   the pre-issue condition
  bug_invert       0.0  F2P 0/1 P2P 139/142 0.0  F2P 0/1 P2P 139/142 0.0  F2P 0/1 P2P 139/142   the added condition is negated
  bug_fieldfilter  0.0  F2P 0/1 P2P 125/142 0.0  F2P 0/1 P2P 125/142 0.0  F2P 0/1 P2P 126/142   the `fields` filter is inverted

  C1  renamed gold, repaired test  reward = 1.0  OK
  C2  bug_revert 0.0 CAUGHT   bug_invert 0.0 CAUGHT   bug_fieldfilter 0.0 CAUGHT
  G1  original gold, repaired test reward = 1.0  OK

  C3  FAIL -- DETECTION DRIFT: the repaired test does not reject what the original rejected
      bug_fieldfilter:
        no longer fails: test_empty_fields_to_construct_instance (model_forms.tests.ModelFormBaseTest)

  -> FAIL
```

The drift is one test inside `125/142 → 126/142`. **The count-based C3 that
shipped with M0d would not have seen it**: the coupled test is PASS_TO_PASS, so
the F2P breakdown is identical (`0/1` under both), and the P2P count moves by one
inside a number the mutant moves by seventeen. C3 was reimplemented for this task
to compare the exact **set** of graded node ids that did not pass, recomputed from
each run's log because `grade_log` truncates `p2p_failing` to ten entries.

## 6. The digest, and the formcheck re-run

```
repaired-run digest_trace:
  06fa9e746014b1e618a250bfddda19984e6eb3cc70a3231694fbb624ff1366c4  memo_hit=False   control
  13fee09df49faa50a83adaca2f654fe43a5d93b114ae6bc773925213276615a9  memo_hit=False   transformed
  13fee09df49faa50a83adaca2f654fe43a5d93b114ae6bc773925213276615a9  memo_hit=True    re-grade
```

Control and transformed differ, so the 1.0 was graded rather than memoized; the
repaired-run control digest also differs from the un-overlaid run's (`6d42ea63…`),
which is how the overlay is known to have landed.

| case | before | after |
|---|---|---|
| **`symbol_rename:construct_instance`** | **WITNESS** | **CLEAN** |

```
witnesses : none
detail    : {"new_name": "construct_instance__renamed", "references_rewritten": 2,
             "files_changed": ["django/forms/models.py"], "files_scanned": 818}
graded    : reward 1.0, f2p 1/1, p2p 142/142, n_parsed 143
```

**What the re-run cannot prove, stated as on every previous task.** Anchors come
only from symbols the gold patch overlaps, so `construct_instance` is the sole
anchor before and after and nothing the repair introduced is probed. Here that
limit bites harder than usual: the repaired test's entry point is
`modelform_factory`, which *is* exported — but formcheck reporting CLEAN says
nothing about whether the test still tests anything. **C3 says it does not.**

**Second confirmation of the M0d finding:** formcheck reports CLEAN on a repair
that fails C3. Two tasks now, in the same repo.

## Verdict, and the answer for the django stratum

**Not shipped.** `django-11433` is a hollowing-out: the only name-free
formulation reaches the same assertion through different code, and the test stops
rejecting the mutant it existed to reject.

Two django tasks, two different failure modes:

| task | class | C1 | C2 | C3 |
|---|---|---|---|---|
| `django-11179` | PRECONDITION | pass | pass | **fail** |
| `django-11433` | HOLLOWING-OUT | pass | pass | **fail** |

Both pass the two conditions that were in force before M0d. Both fail the third.
Neither failure is django-specific — `Collector` and `construct_instance` are
internal symbols with unit tests of their own, which is a property of the test
suite, not of the runner. Django's runner was cleared in M0d and behaved
identically here.

**What this does and does not say.** It says that on 2 of 2 django tasks
attempted, the repair method does not produce a shippable repair, and that the
obstacle is the same in both: a graded suite that unit-tests internal helpers.
It does **not** say the other 12 django tasks are unrepairable — they were not
attempted, and `django-13212`, `django-14311`, `django-14771` and `django-15572`
are the module-attribute shape rather than this one. Per the milestone's own
stopping rule, a third attempt would be volume rather than evidence.

## Artifacts

| | |
|---|---|
| `repair/overlay_positive_django_11433.diff` | the positive control |
| `repair/overlay_importlocal_django_11433.diff` | the collateral/intrinsic diagnostic |
| `repair/overlay_repair_django_11433.diff` | the candidate repair — **evidence, not shipped** |
| `repair/m0e_gate.py`, `repair/m0e_gate_result.json` | the matrix above |
| `repair/records_m0e/{plain,positive,repaired}/` | the three harness runs |
| `repair/test_repair_m0e.py` | all of the above pinned offline |
