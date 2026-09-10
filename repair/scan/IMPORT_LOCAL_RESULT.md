# `import_local` across the 12 — INCOMPLETE, stopped on task 2 of 12

The measurement `REPAIR.md` §9 open item 1 asks for: on each all-fail task, move
the coupled symbol's module-scope import into the test functions that use it,
re-grade under the same rename, and report how much of the suite loss was
attributable to that one line.

**Status: 2 of 12 tasks measured. The run stopped on `django-14376` under the
`recovery == 0` rule and has not been resumed.** The remaining 10 are unmeasured.
No aggregate is reported, because neither measured task qualifies for one.

## The two rows

```
task                   symbol            N   k   recovery   reported/N
django__django-12155   parse_docstring   7   4   3          7/7
django__django-14376   DatabaseClient    9   9   0          7/9   <- stopped here
```

`N` graded tests, `k` still failing after the move, `recovery = N - k`.

**`django-12155` is called out separately, not averaged in: `k = 4`.** The
mechanism established at n=3 in `REPAIR.md` §4 has `k = 1` — one module-scope
import takes the module down, and the single residual is the test whose *subject*
is the symbol. Here four of seven graded tests still fail after the import is
moved, so four reference the symbol directly. That is a different shape and
belongs in no average with the k=1 cases.

**The aggregate attributable to a single module-scope import is therefore
unreported.** Zero of the two measured tasks are k=1 cases. There is nothing yet
to aggregate.

## Why the run stopped, and what the stop means

`recovery == 0` on a task whose control reproduced stops the run as a defect
rather than recording a result. It fired. It was right to fire, and the two
things it separated last time it fired are not the two things here.

**This is not the apparatus defect the rule was written for.** The previous run
(`import_local_run.VOID.json`) died here for a real defect: `str.replace` rewrote
`BaseDatabaseClient` into `BaseDatabaseClient__renamed`, the mysql client failed
to import, and nothing ran. That is fixed (`CHANGES.md` 34). This run's rename is
a clean alpha-rename — the round-trip check passed on all 11 renamed files and
the residue grep is empty — and the test module loaded and executed: `Ran 9
tests`, nine `ERROR` lines, each traceback naming the symbol.

**`recovery = 0` is a genuine property of this task.** All nine graded tests
reach `DatabaseClient`: eight through one shared helper,

```python
class MySqlDbshellCommandTestCase(SimpleTestCase):
    def settings_to_cmd_args_env(self, settings_dict, parameters=None):
        from django.db.backends.mysql.client import DatabaseClient   # moved here
```

and the ninth, `test_crash_password_does_not_leak`, directly. Moving the import
into the helper defers the `ImportError` from module load to call time; it does
not remove it, because the helper *is* the coupling and every graded test calls
it. No placement of that import can save any test here.

So the rule's premise — *"`recovery == 0` cannot happen if the import is what
couples the module"* — is sound, and its antecedent is false on this task. The
module-scope import is not what couples this module. A helper method reached by
every graded test is a second coupling shape, and for it a recovery of zero is an
answer rather than a symptom.

**The rule was not overridden and the run was not resumed.** Whether
`django-14376` is reported as a genuine zero and the run continues on the
remaining 10 is a decision about what the measurement means, not a repair.

## A separate defect this exposed, not fixed here

`reported/N` is `7/9` on `django-14376`: two graded ids were counted as failing
without ever being observed to fail.

```
test_options_override_settings_proper_values (...) ... test_parameters (...) ... ERROR
```

Two result lines on one line. `test_options_override_settings_proper_values` uses
`self.subTest`, and a failing subTest emits its error blocks without terminating
the test's own status line, so the next test's line is appended to it. The parser
attributes results from `test ... STATUS` lines and lost both names. There are
**ten** `ERROR:` blocks for **nine** tests, because that one test errored twice
under two subTest keys.

Here it changed nothing: both tests really did error — their tracebacks are in
the log — so `k = 9` is the right value, reached partly through the
`absent ⇒ failing` branch rather than by observation.

**The direction that would not be harmless is the other one.** `test_parameters`
did emit `... ERROR` and was still lost, because its name sat mid-line. Had it
**passed**, the same swallowing would have counted a passing test as failing —
and for `formcheck` a false failure is a false witness. Whether any task in the
500-task run is affected is not established here and is not assumed either way.
This is `CHANGES.md` 18's family — a log parser that understood one runner — one
level down: a parser that understands one output *shape*.

## Artifacts

`repair/scan/import_local_run.json` — the two rows, written per row,
unconditionally. `repair/scan/import_local_run.VOID.json` — the previous run,
void, kept because it is the record of the substitution defect actually biting.
