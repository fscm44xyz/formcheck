"""Equivalence-preserving transform operators (deterministic, NO LLM).

The mirror image of `m4_mutants.py`. Those operators BREAK behaviour, to check the
graded tests catch them (negative preservation). These operators PRESERVE
behaviour, to check whether the graded tests reject them anyway -- which exhibits
a false negative with a mechanical witness.

Operator implemented here (Phase 0):

  kwonly_specialize -- partial evaluation of a keyword-only parameter whose value
  is a compile-time constant at every call site.

    EQUIVALENCE ARGUMENT (argued, not proven): a keyword-only parameter with a
    constant default, read only in `if <param>` / `if not <param>` tests, and
    passed only as a literal (or omitted) at every call site, is a static switch.
    Specialising the function once per distinct constant and dispatching each
    call site to its specialisation evaluates the same branch, on the same
    arguments, in the same order, as the original. No call site's observable
    behaviour changes. What DOES change is the function's signature -- so a test
    that calls `f(x, param=...)` breaks. That is the point: such a test asserts
    the fix's FORM, not the issue's contract.

    CONFIDENCE: high, GIVEN the four preconditions below. They are checked, and
    the transform refuses rather than guesses when one fails.

    PRECONDITIONS (each checked; failure = refuse, never force):
      P1 signature   the parameter is keyword-only with a Constant default.
      P2 contract    neither the parameter nor the function is named in the issue
                     text (G4, mechanised). If the issue names it, it is
                     candidate CONTRACT -> route to the rubric, do not transform.
      P3 call sites  every call passes the parameter as a Constant, or omits it.
      P4 no dynamic  the parameter is read only in param-only `if` tests inside
                     the function; the function takes no **kwargs.
"""
import ast
import copy


class Refused(Exception):
    """A precondition failed. The transform refuses; the case routes onward."""


def _norm(text):
    """Markdown-normalised text for the mention check: identifiers survive,
    punctuation becomes whitespace, so `consider_mro` matches inside a code
    fence or a sentence but not inside a longer identifier."""
    return "".join(c.lower() if (c.isalnum() or c == "_") else " " for c in text)


def _mentions(text, word):
    return f" {_norm(word).strip()} " in f" {_norm(text)} "


def _find_func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise Refused(f"P1: no function named {name!r}")


def _test_value(test, param, value):
    """The value of an `if` test that depends ONLY on `param`; None if it does not."""
    if isinstance(test, ast.Name) and test.id == param:
        return bool(value)
    if (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)
            and isinstance(test.operand, ast.Name) and test.operand.id == param):
        return not bool(value)
    return None


def _param_ifs(func, param):
    """The `if` nodes inside `func` whose test depends only on `param`."""
    return [n for n in ast.walk(func)
            if isinstance(n, ast.If) and _test_value(n.test, param, True) is not None]


def _call_sites(tree, name):
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == name]


def _lines_of(lines, start, end):
    return lines[start - 1:end]


def _reindent(block, frm, to):
    """Move a source block from column `frm` to column `to`, blanks untouched."""
    out = []
    for ln in block:
        if not ln.strip():
            out.append("")
        elif ln[:frm].strip() == "":
            out.append(" " * to + ln[frm:])
        else:
            raise Refused("reindent: block is not uniformly indented")
    return out


def _specialised_body(func, param, value, lines):
    """Source lines of `func`'s body with every param-only `if` resolved."""
    body = _lines_of(lines, func.body[0].lineno, func.end_lineno)
    offset = func.body[0].lineno
    for node in sorted(_param_ifs(func, param), key=lambda n: n.lineno, reverse=True):
        taken = node.body if _test_value(node.test, param, value) else node.orelse
        if not taken:
            raise Refused("P4: a param-only `if` has an empty taken branch")
        branch = _lines_of(lines, taken[0].lineno, taken[-1].end_lineno)
        branch = _reindent(branch, taken[0].col_offset, node.col_offset)
        lo, hi = node.lineno - offset, node.end_lineno - offset
        body[lo:hi + 1] = branch
    return body


def _header(func, param, new_name):
    """`def <new_name>(<args minus param>) -> <ret>:`, rendered from the AST."""
    d = copy.deepcopy(func)
    d.name = new_name
    keep = [(a, dv) for a, dv in zip(func.args.kwonlyargs, func.args.kw_defaults)
            if a.arg != param]
    d.args.kwonlyargs = [a for a, _ in keep]
    d.args.kw_defaults = [dv for _, dv in keep]
    d.body = [ast.Expr(value=ast.Constant(value=0))]
    d.decorator_list = []
    return ast.unparse(ast.fix_missing_locations(d)).rsplit("\n", 1)[0]


def sibling_name(func_name, param, value):
    """The mechanical, private name of a non-default specialisation."""
    return f"_{func_name}__{param}_{value}"


def kwonly_specialize(src, func_name, param, issue_text, extra_sources=None):
    """Apply the operator to `src`. Returns (new_src, report). Raises Refused.

    `extra_sources` is {path: source} for every OTHER module that may call the
    function. The equivalence argument is repo-wide, so the call-site precondition
    must be too: a caller in another module that flips the parameter would need a
    cross-module rewrite, which this operator does not do -- it refuses instead.
    """
    tree = ast.parse(src)
    func = _find_func(tree, func_name)
    lines = src.splitlines()
    report = {"operator": "kwonly_specialize", "function": func_name,
              "parameter": param, "confidence": "high", "preconditions": {}}

    # --- P1: keyword-only with a Constant default ---
    kwnames = [a.arg for a in func.args.kwonlyargs]
    if param not in kwnames:
        raise Refused(f"P1: {param!r} is not a keyword-only parameter of {func_name}")
    default = dict(zip(kwnames, func.args.kw_defaults))[param]
    if not isinstance(default, ast.Constant):
        raise Refused(f"P1: {param!r} has a non-constant default")
    default_value = default.value
    report["preconditions"]["P1_signature"] = f"keyword-only, default {default_value!r}"

    # --- P2: G4 mechanised -- the issue must not name the parameter or function ---
    named = [w for w in (param, func_name) if _mentions(issue_text, w)]
    if named:
        raise Refused(f"P2: the issue names {named} -- candidate CONTRACT, "
                      "route to the rubric rather than transforming")
    report["preconditions"]["P2_contract"] = (
        f"issue names neither {param!r} nor {func_name!r} -> incidental FORM")

    # --- P3: every call site passes a Constant, or omits the parameter ---
    sites = _call_sites(tree, func_name)
    values = set()
    for call in sites:
        for kw in call.keywords:
            if kw.arg is None:
                raise Refused("P3: a call site forwards **kwargs")
            if kw.arg == param:
                if not isinstance(kw.value, ast.Constant):
                    raise Refused("P3: a call site passes a non-constant for the parameter")
                values.add(kw.value.value)
    external = 0
    for path, other in (extra_sources or {}).items():
        for call in _call_sites(ast.parse(other), func_name):
            external += 1
            for kw in call.keywords:
                if kw.arg == param:
                    raise Refused(
                        f"P3: {path} passes {param!r} -- a cross-module rewrite "
                        "this operator does not perform")
    report["preconditions"]["P3_call_sites"] = (
        f"{len(sites)} call site(s) in this module + {external} in "
        f"{len(extra_sources or {})} other scanned module(s), none of the latter "
        f"passing the parameter; non-default constants passed: "
        f"{sorted(values - {default_value}, key=repr) or 'none'}")

    # --- P4: the parameter is read only inside param-only `if` tests ---
    if func.args.kwarg is not None:
        raise Refused("P4: the function takes **kwargs")
    guarded = {id(n) for ifn in _param_ifs(func, param) for n in ast.walk(ifn.test)}
    stray = [n.lineno for n in ast.walk(func)
             if isinstance(n, ast.Name) and n.id == param and id(n) not in guarded]
    if stray:
        raise Refused(f"P4: {param!r} is read outside a param-only `if` (line(s) {stray})")
    report["preconditions"]["P4_no_dynamic"] = (
        f"read only in {len(_param_ifs(func, param))} param-only `if` test(s); no **kwargs")

    # --- rewrite: specialise at the default, emit a private sibling per other value ---
    blocks = [_header(func, param, func_name)]
    blocks += _specialised_body(func, param, default_value, lines)
    emitted = {}
    for v in sorted(values - {default_value}, key=repr):
        name = sibling_name(func_name, param, v)
        emitted[v] = name
        blocks += ["", ""] + [_header(func, param, name)]
        blocks += _specialised_body(func, param, v, lines)
    out = lines[:func.lineno - 1] + blocks + lines[func.end_lineno:]
    src2 = "\n".join(out) + ("\n" if src.endswith("\n") else "")

    # --- rewrite the call sites (descending, so earlier spans stay valid) ---
    tree2 = ast.parse(src2)
    lines2 = src2.splitlines()
    edits = []
    for call in _call_sites(tree2, func_name):
        passed = [kw for kw in call.keywords if kw.arg == param]
        if not passed:
            continue
        if call.lineno != call.end_lineno:
            raise Refused("P3: a parameterised call site spans multiple lines")
        new = copy.deepcopy(call)
        new.keywords = [kw for kw in new.keywords if kw.arg != param]
        value = passed[0].value.value
        if value != default_value:
            new.func = ast.Name(id=emitted[value], ctx=ast.Load())
        edits.append((call.lineno, call.col_offset, call.end_col_offset,
                      ast.unparse(ast.fix_missing_locations(new))))
    for lineno, c0, c1, text in sorted(edits, reverse=True):
        ln = lines2[lineno - 1]
        lines2[lineno - 1] = ln[:c0] + text + ln[c1:]
    report["call_sites_rewritten"] = len(edits)
    report["siblings_emitted"] = list(emitted.values())

    final = "\n".join(lines2) + ("\n" if src.endswith("\n") else "")
    ast.parse(final)  # the output must at least parse
    return final, report
