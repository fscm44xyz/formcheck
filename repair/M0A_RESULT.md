# repair-M0a item 4 — the overlay surface, proved neutrally

Two runs of `pydata__xarray-4966`, identical except for a test-side overlay that
adds a comment and nothing else. **No repair claim is attached to this.** The
overlay is deliberately inert so that any difference in outcome is the harness,
not a repair.

```bash
~/.venv-fc/bin/python scale/run.py --instance-id pydata__xarray-4966 \
    --records-dir repair/records_m0a/plain

~/.venv-fc/bin/python scale/run.py --instance-id pydata__xarray-4966 \
    --tests-overlay repair/overlay_noop_xarray_4966.diff \
    --records-dir repair/records_m0a/overlay
```

Overlay: `repair/overlay_noop_xarray_4966.diff`, 492 bytes, touching
`xarray/tests/test_coding.py` and nothing else — the single file the task's own
test patch touches. `check_tests_overlay` accepted it offline before the pull.

## The reward is unchanged

| | un-overlaid | overlaid |
|---|---|---|
| control passed | `true` | `true` |
| control reason | `untransformed reference scores 1.0` | `untransformed reference scores 1.0` |
| `error` / `completed` | `None` / `true` | `None` / `true` |
| elapsed | 146.43 s | 140.71 s |

The control is the reward of the **original gold** against the graded suite, and
it is 1.0 on both sides. Adding a comment to the graded test file changed
nothing about the score, which is what an inert overlay must do.

Every downstream verdict is identical too:

```
<control>                            OK
kwonly_specialize:<no anchor>        NOT_APPLICABLE
symbol_rename:UnsignedIntegerCoder   WITNESS
collection_reverse:<no anchor>       NOT_APPLICABLE
message_reword:<no anchor>           NOT_APPLICABLE
```

and the witness row's grading is byte-identical on both sides —
`reward 0.0, f2p 0/4, p2p 17/21, n_parsed 25` — as is its persisted `detail`,
`{"new_name": "UnsignedIntegerCoder__renamed", "references_rewritten": 3, ...}`.

## The digests differ

`digest_trace`, in order: the control tree, then the `symbol_rename` tree twice
(the second is the memo hit that serves the hook's re-grade).

| | un-overlaid | overlaid |
|---|---|---|
| `[0]` control | `3efabffa38cb6cef43af7d0b53afefdcddc8d79a8c9691a132acda018f363f6d` | `dd8b7c2f2a2a0fa4edde8a2bd4cafb16c3d086bd9f5b3170de93dce99fe63a94` |
| `[1]` transformed | `9df28167fdf5ff1eb60048c89f180449c51b570a99b010e9c1eba3f949d8983b` | `d2513bd3776fcbb5c7f31594d4cfeb2a400747d77f1bb10df40000b24a6e9f1e` |
| `[2]` re-grade | same as `[1]`, `memo_hit: true` | same as `[1]`, `memo_hit: true` |

All three differ across the two runs, and the memo still hits within each run —
widening the digest did not degrade into "never memoize".

**Why the control digest is the load-bearing one.** At control time no transform
has run, so `xarray/coding/variables.py` is byte-identical in both runs: base
commit plus the same gold patch. The digest covers exactly two paths — that
target and `xarray/tests/test_coding.py` — so a differing control digest can only
come from the test file. `_tree_digest` shells out to `sha256sum` **inside the
container** (`self.sh` is `docker exec … --workdir /testbed`), so this is a
statement about the bytes in `/testbed`, not about the spec the host assembled.
It is corroborated negatively: `formcheck_reset` raises if `git apply` of the
overlay fails, and both runs completed with `error: None`.

**What it still does not establish**, and why the addendum below exists: that the
graded run *executed* those bytes. A stale `.pyc`, a directive pointing at
another file, or a collection that never reached the module would each move the
digest and change nothing pytest actually ran. A no-op overlay cannot tell those
apart — every one of them still yields 1.0.

**This measurement could not have been taken before item 1.** Under the old
`_tree_digest` both runs would have produced the *same* digest at every step,
because the production targets are identical and the test file was not hashed —
the overlay would have been invisible, and `[1]`/`[2]` would have served the
un-overlaid grading. For the same reason the M4 record's control digest for this
task, `636e5d97…`, is not comparable to either column above: it was computed over
the targets alone.

## Housekeeping

Both runs left nothing resident: `leaked_image: false`, `leaked_containers: []`,
zero xarray images and zero containers after the fact.

Records: `repair/records_m0a/plain/` and `repair/records_m0a/overlay/`.


---

# Addendum — the positive control

A no-op overlay is a negative control: it shows the surface does not perturb a
run. On its own it proves nothing, because "applied and inert" and "silently
dropped" produce the same 1.0. What closes it is a **falsifiable** overlay: one
that must break a named set of graded tests, and does, in the graded log, by its
own message.

Overlay: `repair/overlay_positive_xarray_4966.diff`, 519 bytes, inserting
`assert False, "overlay landed"` as the first statement of
`test_decode_unsigned_from_signed` **only**. Same file, same application point as
the no-op.

```bash
~/.venv-fc/bin/python scale/run.py --instance-id pydata__xarray-4966 \
    --tests-overlay repair/overlay_positive_xarray_4966.diff \
    --records-dir repair/records_m0a/positive
```

Read against the **original gold, no transform**: `control` is the untransformed
reference solution, so this is the real solution's reward against the overlaid
suite.

## (a)/(b) The reward drops, and exactly the four targeted tests fail

```
control.passed : False
control.reason : the untransformed reference solution scored 0.0, not 1.0;
                 F2P 4/4, P2P 17/21; first failing:
                 xarray/tests/test_coding.py::test_decode_unsigned_from_signed[1]
graded         : reward 0.0, f2p_pass 4, f2p_fail 0, p2p_pass 17, p2p_fail 4,
                 n_parsed 25
```

| | baseline (no overlay) | positive control |
|---|---|---|
| `test_decode_unsigned_from_signed[1\|2\|4\|8]` | PASSED ×4 | **FAILED ×4** |
| `test_decode_signed_from_unsigned[1\|2\|4\|8]` | PASSED ×4 | PASSED ×4 |
| the other 17 graded node ids | PASSED ×17 | PASSED ×17 |

All 25 graded node ids are reported in the log; **4 changed state and they are
exactly the four targeted**. Nothing else moved, so the overlay is scoped the way
the contract claims.

The baseline column is derived, not assumed: the un-overlaid control scored 1.0,
and `get_resolution_status` returns `FULL` only when every `FAIL_TO_PASS` and
every `PASS_TO_PASS` succeeded — so every graded test passed at baseline.

## (c) The failure text is verbatim in the graded log

```
>       assert False, "overlay landed"
E       AssertionError: overlay landed
```

Four occurrences, one per parametrization. Matching the message rather than
merely counting failures is what ties the drop to *this* overlay: any breakage
would drop the reward; only this one says `overlay landed`.

## The no-op re-run

```bash
~/.venv-fc/bin/python scale/run.py --instance-id pydata__xarray-4966 \
    --tests-overlay repair/overlay_noop_xarray_4966.diff \
    --records-dir repair/records_m0a/noop_rerun
```

`control.passed: true`, `untransformed reference scores 1.0`, and the same five
verdicts including `symbol_rename:UnsignedIntegerCoder WITNESS`. It reproduces
item 4's digests **bit for bit** — `dd8b7c2f…`, `d2513bd3…`, `d2513bd3…` — so the
overlaid tree is deterministic across runs.

Three trees, three distinct container-side control digests:

| run | control digest |
|---|---|
| no overlay | `3efabffa38cb6cef43af7d0b53afefdcddc8d79a8c9691a132acda018f363f6d` |
| no-op overlay | `dd8b7c2f2a2a0fa4edde8a2bd4cafb16c3d086bd9f5b3170de93dce99fe63a94` |
| positive overlay | `1ab790c5e58c12b1a5862a6788ac099e19f31b6603b1679f2ff98bb44e262bd3` |

## Kept as a pair

Both controls are pinned in `repair/test_repair_m0a.py` against the committed
records, so they run offline in the fast gate. `test_the_control_pair_is_intact`
fails if either record goes missing — verified by hiding the positive record and
watching 5 tests fail with the regeneration command in the message, rather than
skipping. A control that silently stops running is the defect this pair exists to
catch.
