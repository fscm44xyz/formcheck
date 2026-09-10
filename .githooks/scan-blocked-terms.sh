#!/usr/bin/env bash
#
# Scan content for the terms AGENTS.md forbids ("What never enters this
# repository").  Used by the pre-commit and commit-msg hooks, and runnable by
# hand -- which is the only way to cover a tag message, since git has no hook
# that fires on `git tag`.
#
#   scan-blocked-terms.sh --staged        added lines in the index (pre-commit)
#   scan-blocked-terms.sh --file PATH     one file, whole content (commit-msg,
#                                         or a tag message written with -F)
#   scan-blocked-terms.sh --tree          every tracked file (the audit sweep)
#
# Exit 0 clean, 1 something was found, 2 the scanner could not run.

set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
terms_file="$here/blocked-terms.txt"
allow_file="$here/allowed-lines.txt"

# Paths the scanner does not read: the two files that must contain the terms in
# order to define them.
skip_path() {
  case "$1" in
    .githooks/blocked-terms.txt|.githooks/allowed-lines.txt) return 0 ;;
    *) return 1 ;;
  esac
}

die() { printf '%s: %s\n' "scan-blocked-terms" "$1" >&2; exit 2; }

[ -r "$terms_file" ] || die "term list not readable: $terms_file"

tmp="$(mktemp -d)" || die "cannot create a temporary directory"
trap 'rm -rf "$tmp"' EXIT

strip_comments() { sed -e 's/[[:space:]]*$//' -e '/^[[:space:]]*#/d' -e '/^$/d' "$1"; }

strip_comments "$terms_file" > "$tmp/terms"
[ -s "$tmp/terms" ] || die "term list has no patterns: $terms_file"
if [ -r "$allow_file" ]; then strip_comments "$allow_file" > "$tmp/allow"; else : > "$tmp/allow"; fi

# Findings are recorded in a file, not a variable.  scan_stream runs at the end
# of a pipeline and therefore in a subshell, where an incremented variable would
# be discarded and the scanner would print findings and still exit 0 -- a guard
# that reports and does not fire.
: > "$tmp/findings"

# scan_stream <where>  -- reads "lineno<TAB>text" pairs on stdin
#
# One grep over the whole stream, then the allowlist over the few survivors.
# Grepping line by line costs a subprocess per line and makes a large staged
# file unusably slow.
scan_stream() {
  local where="$1" lineno text match
  grep -Ei -f "$tmp/terms" | while IFS=$'\t' read -r lineno text; do
    if [ -s "$tmp/allow" ] && printf '%s\n' "$text" | grep -qEi -f "$tmp/allow"; then
      continue
    fi
    match="$(printf '%s\n' "$text" | grep -oEim1 -f "$tmp/terms")" || match="(pattern matched)"
    printf 'x\n' >> "$tmp/findings"
    printf '  %s:%s\n' "$where" "$lineno" >&2
    printf '    blocked term: %s\n' "$match" >&2
    printf '    in: %.160s\n' "$text" >&2
  done
}

scan_staged() {
  local f
  while IFS= read -r -d '' f; do
    skip_path "$f" && continue
    git diff --cached --no-color -U0 -- "$f" | awk '
      /^@@/ { split($0, a, "+"); split(a[2], b, /[ ,]/); ln = b[1] + 0; hunk = 1; next }
      hunk && /^\+/ { print ln "\t" substr($0, 2); ln++ }
    ' | scan_stream "$f"
  done < <(git diff --cached --name-only --diff-filter=ACMR -z)
}

scan_file() {
  local f="$1"
  [ -r "$f" ] || die "cannot read $f"
  # '#' lines are git's own commentary and are not committed.
  grep -nv '^#' "$f" | sed 's/:/\t/' | scan_stream "$(basename "$f")"
}

scan_tree() {
  local f
  while IFS= read -r -d '' f; do
    skip_path "$f" && continue
    grep -In '' "$f" 2>/dev/null | sed 's/:/\t/' | scan_stream "$f"
  done < <(git ls-files -z)
}

case "${1:---help}" in
  --staged) printf 'Checking staged content against %s\n' "${terms_file#"$PWD"/}" >&2; scan_staged ;;
  --file)   [ $# -ge 2 ] || die "--file needs a path"; scan_file "$2" ;;
  --tree)   printf 'Sweeping every tracked file\n' >&2; scan_tree ;;
  --help|-h) sed -n '3,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *)        die "unknown argument: $1 (try --help)" ;;
esac

findings="$(wc -l < "$tmp/findings" | tr -d '[:space:]')"
if [ "${findings:-0}" -gt 0 ]; then
  printf '\n%s blocked term(s) found. See AGENTS.md, "What never enters this repository".\n' "$findings" >&2
  exit 1
fi
exit 0
