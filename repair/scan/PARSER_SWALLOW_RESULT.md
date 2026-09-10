# Does a swallowed status line put a false failure in the 500-task run?

**No. Zero swallowed graded ids in every stored log of the run, and all 34
witness rows are among the logs scanned.** No witness depends on a swallowed
pass.

## The shape, precisely

Django's verbose runner writes `name ... STATUS`, one line per test. A test whose
status is never written leaves its line unterminated and the next test's line is
appended to it:

```
test_options_override_settings_proper_values (...) ... test_parameters (...) ... ERROR
```

`parse_log_django` touches that line twice and is wrong both times.
`prev_test = line.split(" ... ")[0]` keeps only the first name, and the status
branch does `line.split(" ... ERROR")[0]`, which is the **entire prefix** —
`A (...) ... B (...)`. The map gains a key no test id can equal, and **both** ids
are absent from it. Upstream `test_passed` is `case in status_map and
status_map[case] in (PASSED, XFAIL)`, so an absent id is counted as failing.

**What produces the unterminated line.** One shape, observed:
`self.subTest`. When a subTest fails, its error blocks are emitted without the
parent test's status ever being written — the observed log carries **ten**
`ERROR:` blocks for **nine** tests, because one test errored under two subTest
keys. The parser's own comments name three further interleaving shapes
(`Testing against Django installed in …`, `Internal Server Error: …`, `System
check identified no issues …`), and those it handles: the status lands on a later
line beginning `ok`, and a `prev_test` branch plus three regexes recover it. That
recovery covers **passes only**. There is no equivalent for a `FAIL`/`ERROR`
arriving after interleaved output, and none for two names sharing one line.

**Can the parser tell "status line absent" from "status line consumed"?** Not
while parsing — both come out as an id missing from the map, and nothing in the
return value is marked. But the evidence survives in the output: a real test id
never contains `" ... "`, so a key that does is a consumed line, and the ids
inside it are recoverable by substring. That is the detector used here:

```
swallowed(id)  <=>  id not in status_map  and  id is a substring of another key
```

and it is what makes the question answerable from the stored logs at all.

## Result over the run

```
logs scanned                                        64
  of which graded rows                              63
  witness rows among them                           34 of 34
status-map keys containing " ... "                   0
swallowed graded ids                                 0
swallowed ids whose log shows them PASSING           0
tasks showing the shape                              0 of 500
tasks showing it among the 28 witness tasks          0
```

**The zero is not vacuous.** Absence is what the detector discriminates, so
absence has to occur for a zero to carry information:

```
logs with at least one absent graded id             43 of 64
absent graded ids, total                         2,387
of those, carrying the merging signature             0
```

2,387 graded ids are absent across the run's stored logs — the all-fail shape,
where a module fails to import and reports nothing — and not one of them is
absent because its status line was consumed.

## Coverage, and the rows with no stored log

259 rows ran a graded suite. 63 store a log. The gap is the **196 `CLEAN`
rows**, which store none.

They cannot hide a false failure, and this is a property of the defect rather
than an assumption. Swallowing only ever *removes* ids from the status map; a
removed id is not passed, so it lands in `f2p_fail` or `p2p_fail`, so the reward
is below 1.0, so the row is not `CLEAN`. Checked rather than argued: **all 196
`CLEAN` rows have `reward 1.0`, `f2p_fail 0`, `p2p_fail 0` — no exceptions.** A
swallowed id in any of them would have shown up as a non-zero fail count.

The remaining gap is 7 `UNVALIDATED` rows with no stored log. `UNVALIDATED` is
not a witness, so no published witness rests on them.

## The opposite direction, not checked and not claimed

`parse_log_django` marks `prev_test` PASSED whenever a later line begins with
`ok`. After interleaved output `prev_test` can be the wrong test — on a merged
line it is the *first* name — so that branch can record a pass against a test
that did not pass. That error pushes a row **toward** `CLEAN`, which is **fewer**
witnesses, not more, and it is exactly the direction the missing 196 logs would
be needed to check. It is not established here in either direction, and nothing
above depends on it.

## Standing

The defect is real and is in the upstream parser, not in this repository. It did
not touch the run: no graded id in any stored log was swallowed, and the rows
whose logs are not stored are provably immune to the failure direction. Nothing
in `REPORT.md` changes and no number moves.

`repair/scan/parser_swallow_scan.py`; `repair/scan/parser_swallow_scan.json`.
