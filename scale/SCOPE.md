# Which symbols an operator may transform, and why the answer changed

A demo already in circulation shows `formcheck` refusing to rename
`MarkDecorator` on `pytest-dev__pytest-10356`. Run the current code and that row
is not there. This file says why, before anyone has to ask.

Short version: the refusal was real and the reasoning behind it was sound, but
`MarkDecorator` was in the candidate set because a person put it there, not
because the stated rule selected it. The rule is now applied mechanically, it is
narrower, and it was deliberately **not** widened to bring that row back.

---

## The rule, as `writeup.md` §3.3 states it

> An operator is only offered symbols whose definition the reference patch
> actually overlaps.

The purpose is stated in the same section: without the restriction,
`symbol_rename` would sweep every definition in a module and we could pick the
ones that happened to produce a witness. That is selecting for the outcome, and
it would make "no witness" worthless as a result.

## What Phase 2 actually used

A hand-written set, in `scale/m0_run.py` to this day:

```python
"in_scope": {"get_unpacked_marks", "normalize_mark_list", "store_mark",
             "MarkDecorator"},
```

## What the mechanical rule produces

Changed line numbers come from the diff's own hunk arithmetic
(`changed_lines`); a definition is in scope iff one of those lines falls inside
its `lineno .. end_lineno` range in the real post-patch file
(`symbols_covering`). Both live in `scale/container_task.py`.

On `pytest-10356` the gold patch changes lines 358–414 of
`src/_pytest/mark/structures.py`, which gives:

```
{get_unpacked_marks, store_mark}
```

A class enters scope alongside a method it owns, because the class's line range
contains the method's — no separate rule is needed for that, and it is why the
mechanical rule is not simply "top-level defs".

## Why the two sets differ

| symbol | in gold patch? | how it entered the hand-picked set |
|---|---|---|
| `get_unpacked_marks` | **yes** — rewritten by the patch | mechanically |
| `store_mark` | **yes** — a hunk edits its body | mechanically |
| `normalize_mark_list` | **no** — appears nowhere in the patch | by hand |
| `MarkDecorator` | **no** — see below | by hand |

`MarkDecorator` is the interesting one. It is never named in the gold patch. It
appears only as the class enclosing the `__call__` that git prints after `@@` on
the first hunk:

```
@@ -355,12 +355,35 @@ def __call__(self, *args: object, **kwargs: object):
```

git prints the nearest **preceding** definition in a hunk header, which is very
often one the hunk does not touch. Here the hunk's changed lines start at 358,
past the end of `__call__` and past the end of the class; the patch is editing
module-level code that merely happens to sit below them.

An earlier revision of the M1 code read names out of that header. It admitted
`MarkDecorator.__call__` and, through it, seven `kwonly_specialize` anchors on
`__call__`'s keyword parameters — `ids`, `indirect`, `raises`, `reason`, `run`,
`scope`, `strict` — all symbols the gold patch never modifies. Every one of them
happened to REFUSE, so nothing false was reported. That was luck. The bug is
recorded as `CHANGES.md` entry 5.

## Row by row

| operator : anchor | Phase 2 / M0 | reachable mechanically? | under mechanical rule |
|---|---|---|---|
| `kwonly_specialize : get_unpacked_marks(*, consider_mro=...)` | WITNESS | **yes** | WITNESS with a contract oracle; UNVALIDATED without one |
| `symbol_rename : get_unpacked_marks` | WITNESS | **yes** | **WITNESS** |
| `symbol_rename : store_mark` | CLEAN | **yes** | CLEAN |
| `symbol_rename : normalize_mark_list` | CLEAN | **no** | row absent |
| `symbol_rename : MarkDecorator` | REFUSED | **no** | row absent |
| `collection_reverse : get_unpacked_marks -> return list(...)` | UNVALIDATED | **yes** | UNVALIDATED |
| `message_reword : <no anchor>` | NOT_APPLICABLE | n/a | NOT_APPLICABLE |

**Both rows the headline rests on survive.** The two WITNESSes are anchored under
the mechanical rule, and `symbol_rename:get_unpacked_marks` is still a WITNESS
under it — verified by running the mechanical path against the task
(`scale/run.py --instance-id pytest-dev__pytest-10356`).

The `kwonly_specialize` row needs one distinction, because two different axes
move at once when the whole M1 path runs. Its **anchor** is unaffected by the
scope change: the anchor's symbol is `get_unpacked_marks`, which is in scope
under either rule. What changes its verdict is the **oracle**, not the scope. M0
supplies a hand-written contract oracle for this task (`MarkerSetOracle`, reading
the issue's own scenario through pytest's public `iter_markers()`), and under it
the row is a WITNESS. The generic M1 path has no hand-written oracle for 500
tasks and falls back to `SuiteOracle`, which refuses to judge an operator whose
failure mode is SILENT — so the row comes back UNVALIDATED there. That is the
documented rule of `writeup.md` §4.2, working as intended, and it is why THE
NUMBER is `symbol_rename`-only.

## What is lost, stated plainly

`writeup.md` §3.2 works through the `MarkDecorator` refusal as its example of a
false positive removed — a refusal that once fired on a forward-reference type
annotation and now fires on the real `__all__` entry. That worked example is a
true account of something that ran, and the reasoning in it stands on its own.
What it can no longer be presented as is *what the criterion produces*, because
the criterion does not offer `MarkDecorator` as a candidate at all. §3.2 has been
amended to say so.

## Why the rule was not widened to recover those rows

Because the honest version of "widen it until `MarkDecorator` comes back" is
"widen it until a row we already know is interesting comes back", and that is
selecting for the outcome. §3.3 exists to make that impossible. A rule tuned
against known-good rows would still pass every test we have, and would have lost
the only property that makes a null result meaningful.

The mechanical rule is also, simply, more faithful to the sentence §3.3 already
wrote down. It errs toward reporting less: a symbol it misses costs an anchor and
surfaces as `NOT_APPLICABLE`, whereas a symbol it wrongly admits could place a
transform outside the region the gold patch touched and manufacture a witness
there. Those two errors are not symmetric, and the rule is built to fail in the
direction that costs coverage rather than credibility.

## If you are reproducing the demo

The demo's anchor set is still reachable, because M0 keeps its hand-written
`in_scope` set verbatim — that is deliberate, since `scale/m0_run.py` is the
regression gate that proves the container agrees with the July rig, and both
sides of that comparison must use the same set:

```
~/.venv-fc/bin/python scale/m0_run.py          # the demo's seven rows
~/.venv-fc/bin/python scale/run.py --instance-id pytest-dev__pytest-10356
                                               # the mechanical rule's five
```

Related: `CHANGES.md` entries 5 and 6; `writeup.md` §3.2, §3.3, §4.2.
