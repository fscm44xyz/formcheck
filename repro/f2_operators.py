"""Phase 2 -- the family of equivalence-PRESERVING transforms.

Each operator carries four things, and none of them is optional:

  tier        HIGH   applied automatically.
              MEDIUM applied automatically, but the evidence for its equivalence
                     argument is recorded per-anchor and shown in the overlay.
              BORDER never applied automatically -- routed to the rubric.
  argument    why the transform preserves observable behaviour. ARGUED, not
              proven. Every operator states its own and names what would break it.
  observable  WHICH observable class the transform can change if the argument is
              wrong. The runner compares this against what the task's oracle
              actually watches: if the oracle cannot see that class, the result is
              reported UNVALIDATED, never as a witness. An oracle that cannot
              disconfirm a transform must not be used to confirm it.
  preconditions  checked mechanically; a failure REFUSES, it never forces.

The BORDER rule is G4 mechanised and it overrides tier: if the issue names or
paraphrases the object a transform would touch, that object is candidate CONTRACT
and the case is routed to `judge_rubric.md`, whatever the operator's tier says.
"""
import ast
import re
import copy

from f0_equiv import (  # noqa: F401  (kwonly_specialize is part of the family)
    Refused, kwonly_specialize, _mentions, _find_func, _call_sites,
)

HIGH, MEDIUM, BORDER = "HIGH", "MEDIUM", "BORDER"

# Observable classes a transform can perturb, and therefore what an oracle must
# be able to watch for its result to count as a witness.
OBS_SIGNATURE = "callable signature (arity / parameter names)"
OBS_SYMBOL = "symbol identity (module-level name)"
OBS_ORDER = "order of elements in a returned collection"
OBS_MESSAGE = "human-readable text of an exception message"


class Operator:
    """Base: an equivalence-preserving transform over {path: source}."""

    id = None
    tier = None
    observable = None
    argument = None
    breaks_if = None
    loud_failure = False
    """Whether this operator's ONLY realistic failure mode is loud -- an
    incomplete rewrite that raises `AttributeError`/`ImportError`/`NameError`
    NAMING the symbol the moment the code runs, so the task's own pre-existing
    (PASS_TO_PASS) suite detects it. `AttributeError` is listed first because it
    is the one the `xarray#4966` witness actually produced, through a P2P test
    that reached the symbol as a module attribute.

    The converse -- SILENT failure -- is the criterion for UNVALIDATED: a
    reordered collection, a reworded message, or a changed signature acceptance
    produces no exception at all, so a suite that passes cannot be read as
    confirming equivalence.

    This gates what may be judged on a task with NO independently written
    contract oracle. There, the only behavioural check available is the
    pre-existing test suite, and that suite cannot tell whether the ISSUE's fix
    still works: `pytest-10356` showed a fix-breaking mutant (`bug_none`) passing
    every P2P test. So an operator that changes control flow or data order is
    reported UNVALIDATED on such a task, however plausible its argument. Only a
    pure alpha-rename qualifies: it changes no expression's value, and its one
    failure mode is loud.""" 

    def anchors(self, sources, target, issue_text):
        """Applicable sites in `sources[target]`. Each is a dict with at least
        `label`; `note` carries MEDIUM-tier evidence. Never raises."""
        raise NotImplementedError

    def apply(self, sources, target, anchor, issue_text):
        """Return (new_sources, report). Raises Refused when a precondition fails."""
        raise NotImplementedError

    def _base_report(self, anchor):
        return {"operator": self.id, "tier": self.tier,
                "observable": self.observable, "argument": self.argument,
                "breaks_if": self.breaks_if, "anchor": anchor["label"],
                # Carried on the report, not looked up later by operator id: a
                # task with no bespoke contract oracle decides what it may judge
                # from this flag, and that decision must be made from the same
                # object that produced the transform.
                "loud_failure": self.loud_failure,
                # The symbol this anchor is about, needed to ask whether a test
                # failed because that NAME changed (coupling) or for some other
                # reason (broken behaviour). See `writeup.md` 6.2.
                "name": anchor.get("name", anchor.get("func")),
                "evidence": anchor.get("note"), "preconditions": {}}


# ---------------------------------------------------------------------------


class KwonlySpecialize(Operator):
    id = "kwonly_specialize"
    tier = HIGH
    loud_failure = False  # branch selection is semantic; needs a contract oracle
    observable = OBS_SIGNATURE
    argument = (
        "A keyword-only parameter with a constant default, read only in "
        "param-only `if` tests and passed only as a literal (or omitted) at every "
        "call site, is a static switch. Specialising the function per constant and "
        "dispatching each call site to its specialisation evaluates the same "
        "branch on the same arguments in the same order.")
    breaks_if = (
        "the parameter is read dynamically (**kwargs, getattr, signature "
        "introspection), or a call site passes a non-constant.")

    def anchors(self, sources, target, issue_text):
        found = []
        try:
            tree = ast.parse(sources[target])
        except SyntaxError:
            return found
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
                if isinstance(default, ast.Constant):
                    found.append({"label": f"{node.name}(*, {arg.arg}=...)",
                                  "func": node.name, "param": arg.arg})
        return found

    def apply(self, sources, target, anchor, issue_text):
        extra = {p: s for p, s in sources.items() if p != target}
        new, rep = kwonly_specialize(sources[target], anchor["func"],
                                     anchor["param"], issue_text, extra_sources=extra)
        out = dict(sources)
        out[target] = new
        report = self._base_report(anchor)
        report["preconditions"] = rep["preconditions"]
        report["detail"] = {"call_sites_rewritten": rep["call_sites_rewritten"],
                            "siblings_emitted": rep["siblings_emitted"]}
        return out, report


# ---------------------------------------------------------------------------


class SymbolRename(Operator):
    """Rename a module-level function or class, updating every reference."""

    id = "symbol_rename"
    tier = MEDIUM  # narrowed to HIGH per-anchor when the symbol is `_`-private
    loud_failure = True   # an incomplete rename raises on first use
    observable = OBS_SYMBOL
    argument = (
        "Renaming a definition and every static reference to it -- including "
        "`from X import name` -- is a pure alpha-rename. Nothing observable "
        "changes unless the name is reached by a path the rewrite cannot see.")
    breaks_if = (
        "the name is reached dynamically (a string literal, `getattr`, `__all__`, "
        "an entry point) or from a module outside the scanned set.")
    NEW = "{name}__renamed"

    def anchors(self, sources, target, issue_text):
        found = []
        try:
            tree = ast.parse(sources[target])
        except SyntaxError:
            return found
        for node in tree.body:  # module level only
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                private = node.name.startswith("_")
                pkg_private = any(part.startswith("_")
                                  for part in target.replace("\\", "/").split("/")[:-1])
                if private:
                    tier, note = HIGH, "name is `_`-private by convention"
                elif pkg_private:
                    tier, note = (MEDIUM,
                                  "public name inside a `_`-private package "
                                  f"({target}); not part of the documented API")
                else:
                    tier, note = MEDIUM, "public name; scanned references only"
                found.append({"label": node.name, "name": node.name,
                              "tier": tier, "note": note})
        return found

    @staticmethod
    def _annotation_string_ids(tree):
        """String constants that are FORWARD-REFERENCE TYPE ANNOTATIONS.

        `def f() -> "Name":` and `x: Union["Name", int]` are strings only because
        the name is not yet bound; they are STATIC type references, not dynamic
        reach. Treating them as dynamic over-refuses -- it was the reason
        `MarkDecorator` was refused in pytest-10356, where the cited literal was
        `) -> "MarkDecorator":`. They are renamed along with the symbol rather
        than skipped, so nothing is left stale.

        Every OTHER string occurrence stays a refusal: an `__all__` entry, a
        `mock.patch` target, a `getattr` name. Those really are reached by a path
        an alpha-rename cannot follow."""
        ids = set()

        def collect(node):
            if node is None:
                return
            for n in ast.walk(node):
                if isinstance(n, ast.Constant) and isinstance(n.value, str):
                    ids.add(id(n))

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                collect(node.returns)
                a = node.args
                for arg in (*a.posonlyargs, *a.args, *a.kwonlyargs, a.vararg, a.kwarg):
                    if arg is not None:
                        collect(arg.annotation)
            elif isinstance(node, ast.AnnAssign):
                collect(node.annotation)
        return ids

    @staticmethod
    def _all_entry_ids(tree):
        """String constants that are entries of `__all__` (assigned, augmented
        or annotated). These are dynamic reach by construction: `from m import *`
        and every re-export tool resolve them by name at runtime."""
        ids = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets, value = [node.target], node.value
            else:
                continue
            if value is None or not any(
                    isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
                continue
            for n in ast.walk(value):
                if isinstance(n, ast.Constant) and isinstance(n.value, str):
                    ids.add(id(n))
        return ids

    @staticmethod
    def _imports_module(tree, modname):
        """Does this module import `modname` as a module object it can qualify?"""
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if any(a.name == modname and a.asname is None for a in node.names):
                    return True
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.asname == modname or a.name.split(".")[-1] == modname:
                        return True
        return False

    def apply(self, sources, target, anchor, issue_text):
        name = anchor["name"]
        new_name = self.NEW.format(name=name)
        report = self._base_report(anchor)
        report["tier"] = anchor.get("tier", self.tier)

        if _mentions(issue_text, name):
            raise Refused(f"BORDER: the issue names {name!r} -- candidate CONTRACT, "
                          "route to the rubric")
        report["preconditions"]["contract"] = f"issue does not name {name!r}"

        out, refs = dict(sources), 0
        dynamic = []  # (path, lineno, literal, is_all_entry) -- refused below
        for path, src in sources.items():
            try:
                tree = ast.parse(src)
            except SyntaxError:
                raise Refused(f"could not parse {path}")
            # dynamic-reach check, over PRODUCTION sources only (test files are
            # never in `sources`: the transform changes the solution, not the
            # graded tests, so a `mock.patch("mod.name")` in a test is coupling
            # to detect, not a hazard to refuse on).
            edits = []
            annotations = self._annotation_string_ids(tree)
            all_entries = self._all_entry_ids(tree)
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Constant)
                        and isinstance(node.value, str)
                        and re.search(rf"\b{re.escape(name)}\b", node.value)):
                    continue
                if id(node) not in annotations:
                    # Collect, do not raise yet: the refusal must cite the
                    # STRONGEST hit across the whole scan, not the first file
                    # the directory walk happened to yield (NTFS and ext4
                    # order `_pytest/` and `pytest/` differently). An `__all__`
                    # entry is dynamic reach by construction; a docstring
                    # mention is only a hint.
                    dynamic.append((path, node.lineno, node.value[:40],
                                    id(node) in all_entries))
                    continue
                if node.lineno != node.end_lineno:
                    raise Refused(f"multi-line annotation string in {path}")
                line = src.splitlines()[node.lineno - 1]
                seg = line[node.col_offset:node.end_col_offset]
                for m in re.finditer(rf"\b{re.escape(name)}\b", seg):
                    edits.append((node.lineno, node.col_offset + m.start(),
                                  node.col_offset + m.end()))
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id == name:
                    edits.append((node.lineno, node.col_offset, node.end_col_offset))
                elif isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
                    # rewrite only the identifier on the `def`/`class` line
                    kw = "def " if isinstance(node, ast.FunctionDef) else "class "
                    line = src.splitlines()[node.lineno - 1]
                    col = line.index(kw) + len(kw)
                    edits.append((node.lineno, col, col + len(name)))
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name == name and alias.asname is None:
                            line = src.splitlines()[node.lineno - 1]
                            if name not in line:
                                raise Refused(
                                    f"multi-line import of {name!r} in {path}")
                            col = line.index(name)
                            edits.append((node.lineno, col, col + len(name)))
                elif isinstance(node, ast.Attribute) and node.attr == name:
                    # A QUALIFIED reference to the same symbol -- `variables.X()`
                    # where `variables` is the module that defines X -- is still
                    # the same alpha-rename, so rewrite it. Anything else keeps
                    # the refusal: `.X` on an arbitrary object is a different
                    # attribute that happens to share the name.
                    #
                    # Disclosure: this branch was added AFTER an anchor was
                    # refused for exactly this reason (xarray-4966). It removes a
                    # documented limitation of the operator; it does not change
                    # which task or anchor is examined, and the outcome it
                    # enables can be CLEAN just as easily as WITNESS.
                    modname = target.replace("\\", "/").split("/")[-1][:-3]
                    if isinstance(node.value, ast.Name) and node.value.id == modname \
                            and self._imports_module(tree, modname):
                        line = src.splitlines()[node.lineno - 1]
                        col = line.find(name, node.value.end_col_offset)
                        if col < 0:
                            raise Refused(
                                f"qualified reference to {name!r} spans lines in {path}")
                        edits.append((node.lineno, col, col + len(name)))
                    else:
                        raise Refused(
                            f"attribute access `.{name}` in {path} line "
                            f"{node.lineno} is not a qualified reference to the "
                            "defining module -- outside this operator's scope")
            if dynamic:
                continue  # refused below; nothing more to rewrite
            lines = src.splitlines()
            for lineno, c0, c1 in sorted(set(edits), reverse=True):
                ln = lines[lineno - 1]
                if ln[c0:c1] != name:
                    raise Refused(f"span mismatch rewriting {name!r} in {path}")
                lines[lineno - 1] = ln[:c0] + new_name + ln[c1:]
                refs += 1
            new_src = "\n".join(lines) + ("\n" if src.endswith("\n") else "")
            ast.parse(new_src)
            out[path] = new_src
        if dynamic:
            # Cite: an `__all__` entry before any other literal; a public
            # package path (no `_`-prefixed component) before a private one,
            # because the public re-export is the reach downstream code
            # depends on; then path and line, so the citation is stable.
            def private(path):
                return any(part.startswith("_")
                           for part in path.replace("\\", "/").split("/")[:-1])
            dynamic.sort(key=lambda h: (not h[3], private(h[0]), h[0], h[1]))
            path, lineno, literal, is_all = dynamic[0]
            more = len(dynamic) - 1
            raise Refused(
                f"dynamic reach: {name!r} appears in a non-annotation string "
                f"literal in {path} line {lineno} ({literal!r})"
                + (" -- an `__all__` entry" if is_all else "")
                + (f"; {more} further hit(s)" if more else "")
                + " -- an alpha-rename cannot be argued safe")
        report["preconditions"]["no_dynamic_reach"] = (
            f"{name!r} appears in no string literal across "
            f"{len(sources)} scanned file(s)")
        report["detail"] = {"new_name": new_name, "references_rewritten": refs,
                            "files": sorted(sources)}
        return out, report


# ---------------------------------------------------------------------------


class CollectionReverse(Operator):
    """Reverse a returned collection whose order the issue does not fix.

    Included deliberately, and expected to be REFUSED or UNVALIDATED rather than
    to produce witnesses: it is the operator whose equivalence argument is
    weakest, and the runner is meant to say so out loud instead of hiding it.
    """

    id = "collection_reverse"
    tier = MEDIUM
    loud_failure = False  # reordering is silent by construction
    observable = OBS_ORDER
    argument = (
        "If the issue fixes no order for a returned collection, and no caller "
        "depends on position, order is unspecified and reversing it changes "
        "nothing a consumer may rely on.")
    breaks_if = (
        "any consumer is order-sensitive -- including precedence rules like "
        "'nearest definition wins', which are ordering semantics even when the "
        "issue never writes the word 'order'.")

    def anchors(self, sources, target, issue_text):
        found = []
        try:
            tree = ast.parse(sources[target])
        except SyntaxError:
            return found
        for func in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            for node in ast.walk(func):
                if (isinstance(node, ast.Return) and isinstance(node.value, ast.Call)
                        and isinstance(node.value.func, ast.Name)
                        and node.value.func.id == "list"):
                    found.append({"label": f"{func.name} -> return list(...)",
                                  "func": func.name, "lineno": node.lineno,
                                  "note": "order-sensitivity of consumers not "
                                          "established by this operator"})
        return found

    def apply(self, sources, target, anchor, issue_text):
        report = self._base_report(anchor)
        src = sources[target]
        tree = ast.parse(src)
        target_node = None
        for func in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            if func.name != anchor["func"]:
                continue
            for node in ast.walk(func):
                if isinstance(node, ast.Return) and node.lineno == anchor["lineno"]:
                    target_node = node
        if target_node is None:
            raise Refused("anchor no longer present")
        if target_node.lineno != target_node.end_lineno:
            raise Refused("multi-line return expression")
        lines = src.splitlines()
        ln = lines[target_node.lineno - 1]
        inner = ln[target_node.value.col_offset:target_node.value.end_col_offset]
        lines[target_node.lineno - 1] = (
            ln[:target_node.value.col_offset] + f"list(reversed({inner}))"
            + ln[target_node.value.end_col_offset:])
        new_src = "\n".join(lines) + ("\n" if src.endswith("\n") else "")
        ast.parse(new_src)
        out = dict(sources)
        out[target] = new_src
        report["preconditions"]["order_unspecified"] = (
            "asserted from the issue text only; consumer order-sensitivity is NOT "
            "established -- this is why the tier is MEDIUM and the observable is "
            "element order")
        report["detail"] = {"rewritten_line": target_node.lineno}
        return out, report


# ---------------------------------------------------------------------------


class MessageReword(Operator):
    """Reword an exception message string the issue does not specify."""

    id = "message_reword"
    tier = HIGH
    loud_failure = False  # a consumer matching on text fails quietly
    observable = OBS_MESSAGE
    argument = (
        "An exception's message text is not part of the contract unless the issue "
        "specifies it: the type raised is the contract, the wording is form. "
        "Rewording changes no control flow -- the same exception type is raised "
        "at the same point with the same cause.")
    breaks_if = (
        "a consumer matches on the message text, or the issue quotes the wording "
        "(then it is contract and the anchor is refused).")

    def anchors(self, sources, target, issue_text):
        found = []
        try:
            tree = ast.parse(sources[target])
        except SyntaxError:
            return found
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                for arg in node.exc.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        found.append({"label": f"raise at line {node.lineno}: "
                                               f"{arg.value[:40]!r}",
                                      "lineno": arg.lineno, "text": arg.value})
        return found

    def apply(self, sources, target, anchor, issue_text):
        report = self._base_report(anchor)
        text = anchor["text"]
        if _mentions(issue_text, text) or text.lower() in issue_text.lower():
            raise Refused("BORDER: the issue quotes this message -- CONTRACT, "
                          "route to the rubric")
        src = sources[target]
        new_text = f"[reworded] {text}"
        if src.count(repr(text)) + src.count(f'"{text}"') + src.count(f"'{text}'") != 1:
            raise Refused("message literal is not uniquely locatable")
        for quoted in (f'"{text}"', f"'{text}'"):
            if quoted in src:
                new_src = src.replace(quoted, quoted[0] + new_text + quoted[0], 1)
                break
        else:
            raise Refused("message literal not found in source form")
        ast.parse(new_src)
        out = dict(sources)
        out[target] = new_src
        report["preconditions"]["contract"] = "issue does not quote this message"
        report["detail"] = {"old": text, "new": new_text}
        return out, report


FAMILY = [KwonlySpecialize(), SymbolRename(), CollectionReverse(), MessageReword()]
