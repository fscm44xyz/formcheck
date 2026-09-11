"""Does `SymbolRename.apply` rename the symbol it was asked to rename?

Not a repair-harness question. `repro/f2_operators.py` produced the 28 witnesses
of the published 500-task run, so if its substitution can land on the wrong
identifier, some fraction of those witnesses may be witnesses of a broken rename
rather than of a coupled grader.

THE SHAPE. The operator does NOT use `str.replace` -- it collects AST spans and
rewrites them, which is boundary-correct for `ast.Name` nodes because a Name's
`id` must equal the symbol exactly. Two branches do not use AST spans:

    f2_operators.py:313   col = line.index(name)          # ImportFrom
    f2_operators.py:337   col = line.find(name, ...)      # Attribute

`str.index` is a substring search. On a line where the symbol occurs as a
substring BEFORE the alias -- `from pkg.mod import BaseFoo, Foo` with anchor
`Foo` -- it returns the offset inside `BaseFoo`.

The span check at :347 cannot catch it:

    if ln[c0:c1] != name: raise Refused(...)

because the slice IS exactly `name` -- it is the tail of `BaseFoo`.

WHAT CHANGED. Both branches now take the span from the AST -- the alias node for
the import, the node's own end offset for the attribute -- so all four cases
rename correctly and the probe expects OK on all four. The round-trip invariant
this probe used to apply from the outside also lives INSIDE the operator now, as
a `Refused`, and it is what stood between the substring searches and a silently
broken rename while the fix was being written.

Run `--expect-unfixed` after reverting either branch to a substring search: the
two corrupting cases must come back REFUSED rather than BROKEN. That is the
guard being exercised rather than assumed, and it is the reason this file keeps
its own independent copy of the invariant.

    ~/.venv-fc/bin/python repair/scan/operator_boundary_probe.py
    ~/.venv-fc/bin/python repair/scan/operator_boundary_probe.py --expect-unfixed
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "repro"))

from f0_equiv import Refused          # noqa: E402
from f2_operators import SymbolRename  # noqa: E402

CASES = [
    ("superstring FIRST on the import line -- the django shape",
     {"pkg/mod.py": "class Foo:\n    pass\n",
      "pkg/use.py": "from pkg.mod import BaseFoo, Foo\n\n\ndef go():\n    return Foo()\n"},
     "pkg/mod.py", "Foo", True),
    ("superstring SECOND -- index finds the real alias",
     {"pkg/mod.py": "class Foo:\n    pass\n",
      "pkg/use.py": "from pkg.mod import Foo, BaseFoo\n\n\ndef go():\n    return Foo()\n"},
     "pkg/mod.py", "Foo", False),
    ("symbol as a substring of the MODULE path",
     {"pkg/mod.py": "class Foo:\n    pass\n",
      "pkg/use.py": "from pkg.Foolib import Foo\n\n\ndef go():\n    return Foo()\n"},
     "pkg/mod.py", "Foo", True),
    ("subclassing a superstring, no import collision",
     {"pkg/mod.py": "from pkg.base import BaseFoo\n\n\nclass Foo(BaseFoo):\n    pass\n"},
     "pkg/mod.py", "Foo", False),
]
"""(label, sources, target, anchor name, corrupted_by_the_substring_branches)

The last field marks the two cases the substring branches landed wrong on. The
operator now renames all four cleanly, so all four are expected OK; under
`--expect-unfixed` these two are the ones the round-trip invariant must refuse.
Nothing may come back BROKEN at any stage -- that is the outcome the invariant
exists to remove.
"""

OK, REFUSED, BROKEN = "OK", "REFUSED", "BROKEN"


def run():
    """Return {label: outcome}, printing the operator's output for each case."""
    outcomes = {}
    for label, sources, target, name, _corrupted in CASES:
        print("=== %s" % label)
        try:
            out, rep = SymbolRename().apply(
                sources, target, {"label": name, "name": name},
                "an issue naming nothing")
        except Refused as exc:
            print("  REFUSED: %s\n" % exc)
            outcomes[label] = REFUSED
            continue
        ok = True
        for path in sorted(out):
            if out[path] == sources[path]:
                continue
            print("  --- %s" % path)
            for ln in out[path].splitlines():
                print("      %s" % ln)
            # The same invariant the operator now applies, kept here as an
            # INDEPENDENT check. If the operator's copy is ever weakened, this
            # one still fails the case rather than agreeing with it.
            back = re.sub(r"\b%s__renamed\b" % re.escape(name), name, out[path])
            if back != sources[path]:
                ok = False
                print("      !! not an alpha-rename: substituting "
                      "%s__renamed back does not reproduce the input" % name)
        print("  references_rewritten: %d   -> %s\n"
              % (rep["detail"]["references_rewritten"], "OK" if ok else "BROKEN"))
        outcomes[label] = OK if ok else BROKEN
    return outcomes


def main(expect_unfixed):
    outcomes = run()
    corrupted = {label for label, _s, _t, _n, c in CASES if c}
    expected = {label: (REFUSED if expect_unfixed and label in corrupted else OK)
                for label, _s, _t, _n, _c in CASES}

    print("=" * 72)
    for label, _s, _t, _n, _c in CASES:
        got, want = outcomes[label], expected[label]
        print("  %-8s (expected %-8s) %s%s"
              % (got, want, label, "" if got == want else "   <-- DISAGREES"))

    broken = [l for l, o in outcomes.items() if o == BROKEN]
    refused = [l for l, o in outcomes.items() if o == REFUSED]
    disagreed = [l for l, o in outcomes.items() if o != expected[l]]

    print("\nBROKEN RENAME on %d of %d probe cases." % (len(broken), len(CASES)))
    print("Round-trip invariant fired (REFUSED) on %d of %d:"
          % (len(refused), len(CASES)))
    for l in refused:
        print("   %s" % l)

    if expect_unfixed:
        print("\nRun in --expect-unfixed mode: a substring search is expected back in")
        print("one of the two branches, and a refusal above is the round-trip")
        print("invariant catching what the span check cannot -- `ln[c0:c1]` is")
        print("exactly `name`, being the tail of the superstring it landed in.")

    print("\nBlast radius on the published 500-task run is UNDETERMINED from the")
    print("records: a witness produced this way and a genuine one both fail with")
    print("`cannot import name '<anchor>'`, so the recorded logs cannot separate")
    print("them. Establishing it means re-running the operator over the 28")
    print("tasks' production trees.")

    if disagreed:
        print("\nPROBE FAILED -- measured outcome disagreed with expectation on:")
        for l in disagreed:
            print("   %s" % l)
        return 1
    print("\nProbe agrees with expectation on all %d cases." % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main("--expect-unfixed" in sys.argv[1:]))
