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

    ~/.venv-fc/bin/python repair/scan/operator_boundary_probe.py
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
     "pkg/mod.py", "Foo", False),
    ("superstring SECOND -- index finds the real alias",
     {"pkg/mod.py": "class Foo:\n    pass\n",
      "pkg/use.py": "from pkg.mod import Foo, BaseFoo\n\n\ndef go():\n    return Foo()\n"},
     "pkg/mod.py", "Foo", True),
    ("symbol as a substring of the MODULE path",
     {"pkg/mod.py": "class Foo:\n    pass\n",
      "pkg/use.py": "from pkg.Foolib import Foo\n\n\ndef go():\n    return Foo()\n"},
     "pkg/mod.py", "Foo", False),
    ("subclassing a superstring, no import collision",
     {"pkg/mod.py": "from pkg.base import BaseFoo\n\n\nclass Foo(BaseFoo):\n    pass\n"},
     "pkg/mod.py", "Foo", True),
]


def run():
    broken, disagreed = [], []
    for label, sources, target, name, expect_ok in CASES:
        print("=== %s" % label)
        try:
            out, rep = SymbolRename().apply(
                sources, target, {"label": name, "name": name},
                "an issue naming nothing")
        except Refused as exc:
            print("  REFUSED: %s\n" % exc)
            continue
        ok = True
        for path in sorted(out):
            if out[path] == sources[path]:
                continue
            print("  --- %s" % path)
            for ln in out[path].splitlines():
                print("      %s" % ln)
            # THE INVARIANT, checked by round trip rather than by inspection.
            # An alpha-rename replaces occurrences of the identifier `name` with
            # `name__renamed` and changes nothing else, so substituting the new
            # identifier back -- on a word boundary -- must reproduce the input
            # byte for byte. Anything else means the edit landed somewhere it
            # should not have.
            #
            # Two weaker checks were tried first and both failed on the cases
            # they were written for. Stripping `name + "__renamed"` and looking
            # for a leftover `"__renamed"` passes on `BaseFoo__renamed`, which
            # CONTAINS `Foo__renamed` -- the defect being probed, reproduced in
            # the probe. Scanning tokens for a `__renamed` suffix misses
            # `Foo__renamedlib`, where the edit landed inside a module path.
            back = re.sub(r"\b%s__renamed\b" % re.escape(name), name, out[path])
            if back != sources[path]:
                ok = False
                print("      !! not an alpha-rename: substituting "
                      "%s__renamed back does not reproduce the input" % name)
        print("  references_rewritten: %d   -> %s\n"
              % (rep["detail"]["references_rewritten"],
                 "OK" if ok else "BROKEN RENAME"))
        if not ok:
            broken.append(label)
        if ok != expect_ok:
            disagreed.append(label)
    return broken, disagreed


if __name__ == "__main__":
    broken, disagreed = run()
    print("=" * 72)
    print("BROKEN RENAME on %d of %d probe cases:" % (len(broken), len(CASES)))
    for b in broken:
        print("   %s" % b)
    if disagreed:
        print("\nProbe expectation disagreed with the measured result on: %s"
              % ", ".join(disagreed))
    print("\nCause: f2_operators.py:313 `col = line.index(name)` in the")
    print("ImportFrom branch is a SUBSTRING search. The span check at :347")
    print("cannot catch it -- `ln[c0:c1]` is exactly `name`, being the tail of")
    print("the superstring it landed in.")
    print("\nBlast radius on the published 500-task run is UNDETERMINED from the")
    print("records: a witness produced this way and a genuine one both fail with")
    print("`cannot import name '<anchor>'`, so the recorded logs cannot separate")
    print("them. Establishing it means re-running the operator over the 28")
    print("tasks' production trees.")
