# AGENTS.md

Working rules for this repository, binding on anyone — person or model — who
commits to it.

## What never enters this repository

- **No third-party names.** People are referred to by role if at all.
- **No framing of the work's purpose** beyond what it is technically.
- **No local absolute paths in tracked files.** Sanitise captured exception text
  before it is committed.
- **Upstream attribution is fine and expected.**

This applies to every commit, including commit bodies and tag messages.

### What the rules do and do not reach

The fourth rule is not an exception to the third; it is the boundary that makes
the third usable. The names of dependencies, benchmarks, providers, registries
and the platform this work is built on are technical facts about the work, and
naming them accurately is the point. What the first rule blocks is individuals.

The third rule is about paths that name *this machine and no other*. Container
paths inside captured logs — `/testbed`, `/root`, `/tmp/pytest-of-root` — are
reproducible artefacts and stay. Captured exception text is called out
separately because a traceback carries the path of whatever produced it, which
is the usual way a local path arrives in a tracked file without anyone
deciding to put it there.

### The guard

The term list is `.githooks/blocked-terms.txt`, one extended regular expression
per line, with `.githooks/allowed-lines.txt` holding the documented exceptions.
Both are meant to be edited: the first rule cannot enumerate individual names in
advance, so a name caught by reading is added to the list so that it is caught
by grep next time.

`.githooks/scan-blocked-terms.sh` is the scanner. Three modes:

```bash
.githooks/scan-blocked-terms.sh --staged     # added lines in the index
.githooks/scan-blocked-terms.sh --file PATH  # one file, whole content
.githooks/scan-blocked-terms.sh --tree       # every tracked file (~3s)
```

`--tree` is the audit, re-runnable. It is what turns a one-off sweep into a
standing check.

### Installing the hooks

Hooks are not cloned. Every checkout installs them once:

```bash
git config core.hooksPath .githooks
```

That enables `pre-commit`, which scans staged content, and `commit-msg`, which
scans the subject and body. Verify with `git config core.hooksPath`.

### What the guard cannot do

Stated so that the gap is not mistaken for coverage:

- **Tag messages are not hooked.** Git fires no hook on `git tag`. The rule
  above still binds them; the enforcement is by hand:
  `git tag -a NAME -F msg.txt` after `.githooks/scan-blocked-terms.sh --file
  msg.txt`.
- **`git commit --no-verify` bypasses both hooks.** That is deliberate — a guard
  with no exit invites a worse one. A bypass belongs in the commit body,
  with the reason.
- **`pre-commit` reads added lines only**, not whole files. Content already
  tracked is the business of `--tree`.
- **A term list only catches terms.** It cannot see purpose framing written in
  ordinary words, or a person named in a sentence with no name-shaped tell.
  Reading is still the check; the hook is the floor under it.
