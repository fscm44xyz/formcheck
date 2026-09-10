# repair-M0d — `django__django-11179`, and what django's runner does

Django is 14 of the 28 witness tasks and 18 of the 34 rows. This milestone asks
whether the repair method reaches half the corpus.

**Summary: django's runner does not block the method. This task's coupling does
not repair cleanly anyway, for a reason that has nothing to do with django — and
the way it fails exposed a gap in the two conditions themselves.**

## The pick

Criterion, fixed before inspection: the `from … import` shape, single-file gold
patch, then lexicographic instance id. Django witness tasks meeting the first
two: `11179`, `11433`, `15380`, `15851`, `15973`. Lexicographic gives
**`django__django-11179`**, anchor `Collector` — `p2p_coupling`, 41 graded tests,
all 41 failing under the rename.

## 1. Does the positive control work under django's runner?

**Yes. A landed overlay is distinguishable from a dropped one.**

`repair/overlay_positive_django_11179.diff` inserts
`assert False, "overlay landed"` into `test_fast_delete_fk` only.

```
control.passed : False
control.reason : ... scored 0.0, not 1.0; F2P 1/1, P2P 39/40;
                 first failing: test_fast_delete_fk (delete.tests.FastDeleteTests)
graded         : reward 0.0, f2p_pass 1, f2p_fail 0, p2p_pass 39, p2p_fail 1,
                 n_parsed 43
p2p_failing    : ['test_fast_delete_fk (delete.tests.FastDeleteTests)']
"overlay landed" in graded_log : True (2 occurrences)
      assert False, "overlay landed"
      AssertionError: overlay landed
```

Exactly the targeted node id fails, by its own message, and the other 40 pass.
The `unittest.loader._FailedTest` problem is specific to *import* failure; a test
that runs and fails is reported per-test with a normal node id, and django's
parser maps it.

## 2. What the loader does under the rename

With `Collector` renamed, `tests/delete/tests.py` does not import, and the run is:

```
tests (unittest.loader._FailedTest) ... ERROR
ERROR: tests (unittest.loader._FailedTest)
ImportError: Failed to import test module: tests
  File "/testbed/tests/delete/tests.py", line 4, in <module>
    from django.db.models.deletion import Collector
ImportError: cannot import name 'Collector'
Ran 1 test in 0.000s
FAILED (errors=1)
```

Parsed, the status map holds **two** entries, both synthetic:

```
'tests (unittest.loader._FailedTest)': ERROR
'tests': ERROR
```

**Zero of the 41 graded node ids are present.** All 41 are then scored failures
by `test_failed`:

```python
def test_failed(case, sm): return case not in sm or sm[case] in [FAILED, ERROR]
```

**Is absence distinguishable from "ran and failed"?**

* **At the reward level, no — and not merely in practice.** That is one
  expression: `case not in sm` and `sm[case] == FAILED` are the same branch of
  the same `or`. `test_failed(absent, sm)` and `test_failed(id, {id: 'FAILED'})`
  both return `True`. No consumer of `reward` can separate them, on any repo.
  django is where it becomes conspicuous, not where it becomes true.
* **At the log level, yes, plainly.** `Ran 1 test`, the `_FailedTest` name and
  the `ImportError` are all in the log, and formcheck's attribution reads the
  log rather than the status map. On this task it classified all reported
  failures as coupled: `broke=0`, `unparsed=0`,
  `all_reference_the_symbol=True`.

**Consequence for the two conditions: both remain evaluable.** C1 asks for reward
1.0, which absence can never produce — 1.0 requires every graded id present *and*
passing. C2 asks for 0.0, which absence *can* produce spuriously: a mutant that
breaks the import for any reason at all scores 0.0 and would read as CAUGHT.

That hole is real and is now closed rather than tolerated. `gate.py` records
`graded_ids_present` per run and requires every mutant to report as many graded
node ids as the gold did; a mutant that ran no tests is flagged as
*"this 0.0 is ABSENCE, not detection"*. **This tightens the gate for every task
and is not an accommodation of django's runner** — no condition was relaxed to
let this case through.

## 3. The coupled test

`tests/delete/tests.py` has 42 test methods, 41 of them graded. `Collector` is
named exactly **twice** in the file:

```
  4: from django.db.models.deletion import Collector       <- module scope
478:         collector = Collector(using='default')         <- one test
```

Both are added by the task's own **test patch**. The coupling did not pre-exist
the benchmark; the benchmark introduced it.

The coupled test is the single FAIL_TO_PASS test:

```python
def test_fast_delete_instance_set_pk_none(self):
    u = User.objects.create()
    # User can be fast-deleted.
    collector = Collector(using='default')                 # entry point
    self.assertTrue(collector.can_fast_delete(u))          # PRECONDITION
    u.delete()
    self.assertIsNone(u.pk)                                # THE CONTRACT
```

`assertIsNone(u.pk)` is the issue's contract. `assertTrue(collector.can_fast_delete(u))`
is a **precondition**: it pins that the *fast* path is the one being exercised,
which matters because the gold patch adds the pk-nulling to the fast path only —
the slow path has always done it.

### The three-variant split

| variant, under the rename | F2P | P2P | reward |
|---|---|---|---|
| shipped test module | 0/1 | 0/40 | 0.0 |
| `import_local` | 0/1 | **40/40** | 0.0 |
| `repaired` | 1/1 | 40/40 | **1.0** |

**40 of the 41 failures were the module-scope import line.** The 41st is the one
test that names the symbol. This is the astropy result again, in a second repo
and a different runner: candidate pattern 2 now holds at n = 2.

## 4. Why it does not repair cleanly

`Collector` is **not public**: no `__all__` in `django/db/models/deletion.py`, and
it is not re-exported from `django.db.models`. Unlike `decode_cf` and
`separability_matrix`, there is no exported symbol that reaches the same
behaviour. So the entry-point substitution of candidate pattern 1 is unavailable,
and the only formulation that removes the name is to **delete the precondition**:

```diff
     def test_fast_delete_instance_set_pk_none(self):
         u = User.objects.create()
-        # User can be fast-deleted.
-        collector = Collector(using='default')
-        self.assertTrue(collector.can_fast_delete(u))
         u.delete()
         self.assertIsNone(u.pk)
```

**A behavioural substitute was looked for and measured, not assumed.** The
obvious candidate is a query count — a fast delete should be one query. Measured
inside the image, with `can_fast_delete` forced to return `False`:

```
PROBE can_fast_delete: True      nqueries: 1   sql: DELETE FROM "delete_user" ...  pk after: None
PROBE can_fast_delete: False     nqueries: 1   sql: DELETE FROM "delete_user" ...  pk after: None
```

Identical. After the gold patch the two paths are observationally equivalent for
this input — same query count, same SQL, same resulting pk. `assertNumQueries(1)`
would be a **vacuous** precondition here. There is no public observable that
separates the paths.

### What deleting the precondition costs — measured

```
django__django-11179  --  reward by (test variant x solution)

  solution                         original             import_local                 repaired   effect
  gold               1.0  F2P 1/1 P2P 40/40   1.0  F2P 1/1 P2P 40/40   1.0  F2P 1/1 P2P 40/40
  gold_renamed        0.0  F2P 0/1 P2P 0/40   0.0  F2P 0/1 P2P 40/40   1.0  F2P 1/1 P2P 40/40
  bug_revert         0.0  F2P 0/1 P2P 40/40   0.0  F2P 0/1 P2P 40/40   0.0  F2P 0/1 P2P 40/40   the pre-issue behaviour: the fast path leaves the pk set
  bug_zero           0.0  F2P 0/1 P2P 40/40   0.0  F2P 0/1 P2P 40/40   0.0  F2P 0/1 P2P 40/40   the pk is cleared to 0 rather than None
  bug_nofast         0.0  F2P 0/1 P2P 30/40   0.0  F2P 0/1 P2P 30/40   0.0  F2P 1/1 P2P 30/40   fast deletion disabled -- the path the issue is about is never taken

  C1  renamed gold, repaired test  reward = 1.0  OK
  C2  bug_revert 0.0 CAUGHT   bug_zero 0.0 CAUGHT   bug_nofast 0.0 CAUGHT
  G1  original gold, repaired test reward = 1.0  OK

  !! DETECTION DRIFT -- the repaired test catches less than the original:
       bug_nofast       F2P 0/1 -> 1/1
```

**Both conditions pass. The repair is still a hollowing-out.** `bug_nofast`
disables fast deletion — precisely the regression the deleted precondition
existed to catch. Under the original test the F2P test fails (0/1). Under the
repaired test it **passes** (1/1): the slow path nulls the pk too, so the contract
assertion is satisfied by a program that never runs the code the issue is about.

The task-level reward is still 0.0, so C2 is satisfied — but only because ten
*other* P2P tests happen to catch `bug_nofast`. The repaired test itself stopped
detecting it.

## The finding that outranks the repair

**C2, measured at the reward level, cannot detect a hollowing-out when the suite
has redundancy.** A repaired test can lose its own discriminating power entirely
and the gate will still read `0.0 CAUGHT`, because some other test covers the
mutant. Reward is a property of the suite; "was this test weakened" is a property
of the test, and the two come apart exactly when other tests overlap.

This was invisible in M0b and M0c — in both, every mutant's F2P breakdown was
identical under the original and repaired tests, so there was nothing to see. It
took a case where the repair genuinely lost something to expose that the
condition could not have told us.

`gate.py` now reports **detection drift** — any mutant whose F2P breakdown differs
between the original and repaired tests — separately from C2. It does not flip the
verdict on its own, because the reward is what the reward is; it says what the
reward cannot.

**And formcheck reports CLEAN on this repair.** Before: `symbol_rename:Collector
WITNESS`. After: `CLEAN`, reward 1.0, no witnesses, on a genuinely distinct tree
(control `ff3183bb…` vs transformed `0ffe1976…`). A repair can pass formcheck,
pass C1, pass C2, and still be strictly weaker than what it replaced.

## Verdict

**Not shipped.** `django-11179` is reported as *not cleanly repairable*: the
coupled call is a precondition on a non-public object with no observable public
proxy, and the only name-free formulation costs the test its specificity. The
diff, the gate result and the drift measurement are kept as the evidence for
that, not as a repair to apply.

**Django's runner is not the obstacle.** The positive control works, the log
distinguishes absence from failure, and both conditions are evaluable. Nothing
here blocks repairing the other 13 django tasks; this particular task's coupling
is the problem, and its shape — a precondition assertion on an internal — is not
django-specific.

## Two gate defects this case found

1. **The rename was incomplete and looked like a failed repair.** The first run
   renamed `Collector` in `deletion.py` only. It is referenced from five django
   modules, so the library broke and the test module failed to import in *every*
   variant — including the repaired one, which no longer mentions the symbol. The
   reward was 0.0 throughout and read exactly like "the repair does not work".
   `gate.build` now greps production sources for the old name after renaming and
   raises on any residue. Confirmed against the real operator afterwards:
   `detail.files_changed` lists the same five files, `references_rewritten: 9`.
2. **The mutant anchor was ambiguous.** `setattr(instance, model._meta.pk.attname,
   None)` appears twice — the gold adds it to the fast path, the slow path always
   had it. The gate's existing anchor guard refused rather than editing the wrong
   one. That guard was written for M0b and paid for itself here.

## Artifacts

| | |
|---|---|
| `repair/overlay_positive_django_11179.diff` | the positive control |
| `repair/overlay_importlocal_django_11179.diff` | the collateral/intrinsic diagnostic |
| `repair/overlay_repair_django_11179.diff` | the candidate repair — **evidence, not shipped** |
| `repair/m0d_gate.py`, `repair/m0d_gate_result.json` | the matrix above |
| `repair/records_m0d/{plain,positive,repaired}/` | the three harness runs |
| `repair/test_repair_m0d.py` | all of the above pinned offline, drift included |
