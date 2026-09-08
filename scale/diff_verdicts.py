"""Field-by-field diff of a container run against the July rig's Phase 2 table.

The gate for M0 is not "the same number of witnesses". It is that every row
agrees on operator, anchor, verdict AND, where there is one, the refusal reason
string -- because a refusal that lands on the right verdict for the wrong reason
is exactly the failure `writeup.md` §3.2 records: `symbol_rename` once refused
`MarkDecorator` on a forward-reference type annotation while never seeing the
`__all__` entry that is the real reason. Same verdict, unsound argument. Only
the reason string distinguishes them, so only the reason string can gate them.

No claim of a match is made anywhere without this diff being printed.
"""

import json


def index_reference(rows):
    """`repro/f2_verdicts.json` -> {(operator, anchor): (verdict, reason)}."""
    out = {}
    for row in rows:
        anchor = row.get("anchor")
        reason = row.get("reason") or row.get("note")
        out[(row["operator"], anchor)] = (row["verdict"], reason)
    return out


def index_run(log):
    """The hook's own `formcheck_log` -> the same shape.

    `<control>` is not a transform row; it is checked separately, because a
    control that did not reach 1.0 means no row below it is evidence at all.
    """
    out = {}
    for label, verdict, why in log:
        if label == "<control>":
            continue
        operator, _, anchor = label.partition(":")
        out[(operator, None if anchor == "<no anchor>" else anchor)] = (verdict, why)
    return out


REASON_REQUIRED = {"REFUSED"}


def diff(reference, run):
    """Rows that differ, as (key, field, expected, got)."""
    problems = []
    for key in sorted(set(reference) | set(run), key=lambda k: (k[0], k[1] or "")):
        want, got = reference.get(key), run.get(key)
        if want is None:
            problems.append((key, "row", "<absent>", got[0]))
            continue
        if got is None:
            problems.append((key, "row", want[0], "<absent>"))
            continue
        if want[0] != got[0]:
            problems.append((key, "verdict", want[0], got[0]))
        if want[0] in REASON_REQUIRED and want[0] == got[0]:
            # Normalised on whitespace only. The wording is the finding.
            a = " ".join((want[1] or "").split())
            b = " ".join((got[1] or "").split())
            if a != b:
                problems.append((key, "reason", a, b))
    return problems


def render(reference, run, problems):
    lines = ["", "  reference = repro/f2_verdicts.json (July rig, host venv)",
             "  run       = this container, through Task.formcheck", "",
             f"  {'operator':20s} {'anchor':42s} {'reference':15s} {'run':15s}"]
    lines.append("  " + "-" * 94)
    for key in sorted(set(reference) | set(run), key=lambda k: (k[0], k[1] or "")):
        want = (reference.get(key) or ("<absent>", None))[0]
        got = (run.get(key) or ("<absent>", None))[0]
        mark = " " if want == got else "X"
        anchor = (key[1] or "<no anchor>")[:42]
        lines.append(f"{mark} {key[0]:20s} {anchor:42s} {want:15s} {got:15s}")
    lines.append("")
    if problems:
        lines.append(f"  {len(problems)} DIFFERENCE(S):")
        for key, field, want, got in problems:
            lines.append(f"    {key[0]}:{key[1] or '<no anchor>'}  [{field}]")
            lines.append(f"      reference: {want}")
            lines.append(f"      run      : {got}")
    else:
        lines.append("  IDENTICAL on operator, anchor, verdict and refusal reason.")
    return "\n".join(lines)


def counts(index):
    out = {}
    for verdict, _ in index.values():
        out[verdict] = out.get(verdict, 0) + 1
    return out


def compare(reference_path, log):
    with open(reference_path, encoding="utf-8") as f:
        reference = index_reference(json.load(f))
    run = index_run(log)
    problems = diff(reference, run)
    return {
        "reference_counts": counts(reference),
        "run_counts": counts(run),
        "problems": [
            {"key": f"{k[0]}:{k[1] or '<no anchor>'}", "field": f,
             "reference": w, "run": g} for k, f, w, g in problems
        ],
        "identical": not problems,
        "table": render(reference, run, problems),
    }
