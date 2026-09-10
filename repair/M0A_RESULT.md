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
come from the test file. That is direct evidence the overlay reached the
container and landed in the tree, independent of anything the log says. It is
corroborated negatively: `formcheck_reset` raises if `git apply` of the overlay
fails, and both runs completed with `error: None`.

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
