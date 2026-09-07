"""SYNTHETIC PROBE -- is mock-based coupling reachable by `symbol_rename`?

NOT a measurement. This injects coupling that the real task does not have, to
settle a MECHANISM question I got wrong in the Phase 4.2 report. I claimed there
that `symbol_rename` structurally cannot exhibit `mock_internal` coupling,
because `mock.patch` targets are string literals and the operator refuses on
string occurrences of the name.

That reasoning was wrong. The operator only ever scans PRODUCTION sources -- test
files are never in its source set, because the transform rewrites the solution,
not the graded tests. So a `mock.patch("mod.sym")` inside a test triggers no
refusal at all: the rename proceeds, and the test breaks because it named the
symbol. That is a witness, not a refusal.

The probe: take `store_mark` on pytest-10356, which is CLEAN today, add a
`mock.patch` on it to a PASS_TO_PASS test, and re-run the operator. If the result
turns into a witness, mock coupling is reachable and the Phase 4.2 claim needs
correcting. Run under .venv-pytest; grading is printed from the log.
"""
import os
import re
import sys
import json
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_case  # noqa: E402
import f2_worker  # noqa: E402
from f2_operators import SymbolRename  # noqa: E402

META = json.load(open(os.path.join(HERE, "meta.json")))
P2P = META["PASS_TO_PASS"] if isinstance(META["PASS_TO_PASS"], list) else eval(
    META["PASS_TO_PASS"])
SYMBOL = "store_mark"
TARGET_TEST = "test_pytest_param_id_requires_string"   # a PASS_TO_PASS test
INJECT = [
    "    from unittest import mock as _probe_mock",
    '    with _probe_mock.patch("_pytest.mark.structures.{sym}"):',
    "        pass",
]


def inject_mock_patch():
    """Add a mock.patch on SYMBOL to the body of a PASS_TO_PASS test."""
    path = os.path.join(run_case.REPO, "testing", "test_mark.py")
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    for i, line in enumerate(lines):
        m = re.match(rf"^def {TARGET_TEST}\(", line)
        if m:
            body = i + 1
            while body < len(lines) and (not lines[body].strip()
                                         or lines[body].lstrip().startswith(('"', "'"))):
                body += 1
            block = [ln.format(sym=SYMBOL) for ln in INJECT]
            lines[body:body] = block
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            return True
    return False


def run(symbol, with_injection):
    f2_worker.reset()
    run_case.apply_patch(os.path.join(HERE, "tests.diff"))
    run_case.apply_patch(os.path.join(HERE, "gold.diff"))
    if with_injection and not inject_mock_patch():
        raise SystemExit(f"could not find {TARGET_TEST} to inject into")
    op = SymbolRename()
    target = f2_worker.TARGET
    base = {target: open(os.path.join(run_case.REPO, *target.split("/")),
                         encoding="utf-8").read()}
    issue = open(os.path.join(HERE, "issue.txt"), encoding="utf-8").read()
    anchor = [a for a in op.anchors(base, target, issue) if a["name"] == symbol][0]
    sources = f2_worker.read_sources(must_contain=symbol)
    sources[target] = base[target]
    new, _ = op.apply(sources, target, anchor, issue)
    f2_worker.write_sources(new)
    r = subprocess.run(
        [run_case.PY, "-m", "pytest", "-rA", "-p", "no:cacheprovider",
         run_case.TEST_FILE],
        cwd=run_case.REPO, capture_output=True, text=True, timeout=900)
    log = run_case.TEST_CMD_ECHO + "\n" + r.stdout + "\n" + r.stderr
    f2_worker.reset()
    return log


def sections_of(log):
    """`____ header ____` blocks. These are NOT all failures -- a passing test
    that runs a nested pytest prints one too, which is exactly why the classifier
    looks up only the tests pytest actually reported as FAILED."""
    out, current, buf = {}, None, []
    for line in log.splitlines():
        m = re.match(r"^_{3,}\s+(.+?)\s+_{3,}$", line)
        if m:
            if current is not None:
                out[current] = "\n".join(buf)
            current, buf = m.group(1).strip(), []
        elif current is not None:
            buf.append(line)
    if current is not None:
        out[current] = "\n".join(buf)
    return out


def names_symbol(text, name):
    """Mirrors the fixed `f4_formcheck.names_symbol`. The mock phrasing was
    missing from it until this probe exposed the gap."""
    return (f"has no attribute '{name}'" in text
            or f"does not have the attribute '{name}'" in text
            or f"name '{name}' is not defined" in text
            or f"cannot import name '{name}'" in text)


def main():
    run_case.assert_editable_pytest()
    print("SYNTHETIC PROBE -- mock coupling reachability (not a measurement)\n")
    for injected in (False, True):
        log = run(SYMBOL, injected)
        sections = sections_of(log)
        # pytest's own suite runs NESTED pytest sessions, so the outer log also
        # carries `FAILED test_select_simple.py::...` lines from inner runs.
        # Keep only ids in the graded file. The real classifier is not exposed to
        # this at all: it takes its failing set from the grader's F2P/P2P id
        # lists, not from the log text.
        failed = [t for t in re.findall(r"^FAILED (\S+)", log, re.M)
                  if t.startswith(run_case.TEST_FILE + "::")]

        def body_for(test_id):
            tail_id = test_id.split("::")[-1].split("[")[0]
            for header, body in sections.items():
                if header.split(".")[-1].split("[")[0] == tail_id:
                    return body
            return ""

        tail = [ln for ln in log.splitlines() if " passed" in ln or " failed" in ln]
        label = "WITH injected mock.patch" if injected else "baseline (real task)"
        print(f"  {label}:")
        print(f"    {tail[-1].strip() if tail else '?'}")
        print(f"    tests reported FAILED: {failed or 'none'}")
        if not failed:
            print("    -> verdict CLEAN (nothing failed)\n")
            continue
        for test_id in failed:
            first = [ln.strip() for ln in body_for(test_id).splitlines()
                     if ln.startswith("E ")]
            print(f"    {test_id.split('::')[-1]}: {(first[0] if first else '?')[:84]}")
        allnamed = all(names_symbol(body_for(t), SYMBOL) for t in failed)
        print(f"    every failing test references {SYMBOL!r}: {allnamed}"
              f"  -> verdict {'WITNESS' if allnamed else 'INVALID'}\n")


if __name__ == "__main__":
    main()
