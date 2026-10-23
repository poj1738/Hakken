#!/usr/bin/env bash
# Orient whoever just opened this repo: where you are, what moved, what is next.
#
# Run by the SessionStart hook in .claude/settings.json, and safe to run by hand.
# Read-only: it never fetches, commits, or changes a branch. Every section degrades
# gracefully -- no gh, no network, no PROGRESS.md: it says so and carries on.

set -uo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)" || exit 0

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
dim()  { printf '\033[2m%s\033[0m\n' "$1"; }

echo
bold "── Hakken · session start ─────────────────────────────────"

# -- branch ----------------------------------------------------------------
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
echo "  branch: ${branch}"
if [ "${branch}" = "main" ]; then
  echo "          ^ work on a branch: git checkout -b <name>/<topic>"
fi

# -- divergence from origin/main ------------------------------------------
# Deliberately NOT fetching: a hook must not touch the network. This compares
# against the last-fetched origin/main, so run `git pull origin main` yourself.
if git rev-parse --verify --quiet origin/main >/dev/null; then
  behind="$(git rev-list --count HEAD..origin/main 2>/dev/null || echo '?')"
  ahead="$(git rev-list --count origin/main..HEAD 2>/dev/null || echo '?')"
  echo "  vs origin/main (as last fetched): ${behind} behind, ${ahead} ahead"
  [ "${behind}" != "0" ] && [ "${behind}" != "?" ] && echo "          ^ git pull origin main"
else
  echo "  vs origin/main: no origin/main ref locally"
fi

# -- uncommitted work ------------------------------------------------------
dirty="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
if [ "${dirty}" = "0" ]; then
  echo "  working tree: clean"
else
  echo "  working tree: ${dirty} uncommitted change(s)"
  git status --porcelain 2>/dev/null | head -8 | sed 's/^/            /'
  [ "${dirty}" -gt 8 ] && dim "            ... and $((dirty - 8)) more"
fi

# -- progress --------------------------------------------------------------
echo
if [ -f PROGRESS.md ]; then
  bold "  PROGRESS.md"
  sed -n 's/^\*\*Last updated:\*\* /            updated: /p' PROGRESS.md | head -1
  # "## Status" paragraph: the first bolded line after the heading.
  awk '/^## Status/{f=1;next} f&&/^\*\*/{gsub(/\*\*/,""); print "            " $0; exit}' PROGRESS.md
  # "## Blocked on" first real line.
  awk '/^## Blocked on/{f=1;next} f&&NF&&!/^#/{gsub(/\*\*/,""); print "            blocked: " $0; exit}' PROGRESS.md
  echo
  bold "  Next up"
  awk '/^## Next up/{f=1;next} /^## /{if(f)exit} f&&NF{gsub(/\*\*/,""); print}' PROGRESS.md \
    | head -8 | sed 's/^/            /'
else
  dim "  PROGRESS.md missing - create it (see CLAUDE.md, Team workflow)"
fi

# -- latest 3 handoff entries ---------------------------------------------
echo
if [ -f docs/HANDOFF.md ]; then
  bold "  Latest handoff entries (newest first)"
  # `fence` toggles on ``` lines so the template block inside the fence is not
  # mistaken for a real entry. Bold markers are stripped for terminal reading.
  awk '
    /^```/   { fence = !fence; next }
    fence    { next }
    /^### /  { n++; if (n > 3) exit; print "            " $0; next }
    n >= 1 && /^\*\*(Broken|Needs from teammates|Next):\*\*/ {
                 gsub(/\*\*/, ""); print "              " $0 }
  ' docs/HANDOFF.md | head -40
  if ! awk '/^```/{f=!f;next} f{next} /^### /{found=1} END{exit !found}' docs/HANDOFF.md; then
    dim "            (no entries yet)"
  fi
else
  dim "  docs/HANDOFF.md missing - create it (see CLAUDE.md, Team workflow)"
fi

# -- open PRs (optional: needs gh) ----------------------------------------
echo
if command -v gh >/dev/null 2>&1; then
  if gh auth status >/dev/null 2>&1; then
    bold "  Open PRs"
    if ! gh pr list --limit 10 --json number,title,headRefName,isDraft \
         --template '{{range .}}            #{{.number}} {{.headRefName}} — {{.title}}{{if .isDraft}} (draft){{end}}
{{end}}' 2>/dev/null; then
      dim "            (could not list PRs)"
    fi
  else
    dim "  Open PRs: gh installed but not logged in - run: gh auth login"
  fi
else
  dim "  Open PRs: gh not installed - skipping (brew install gh)"
fi

echo
dim "  Session end: make test · scripts/secret_scan.py --all · update PROGRESS.md"
dim "               + docs/HANDOFF.md, then push and open a PR. Never commit .env."
bold "───────────────────────────────────────────────────────────"
echo
