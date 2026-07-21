#!/usr/bin/env bash
# leak-check — pre-publish sanitization gate.
#
# Scans every tracked file for (a) structural leaks and (b) your private term
# blocklist. The blocklist lives in scripts/leak-terms.local.txt (gitignored,
# one term per line, optional "term<TAB>ALLOW:<path>[,<path>...]" to allowlist
# one or more files) —
# committing the list would itself disclose what you sanitized away.
#
# Exit 0 = clean. Exit 1 = hits printed. Run before every push of a repo that
# mirrors private config.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

fail=0
files=$({ git ls-files; git ls-files --others --exclude-standard; } |
  grep -v '^scripts/leak-check.sh$' | sort -u)

echo "== structural checks =="
# 1. Absolute home paths (machine-specific, often embed a username)
if hits=$(echo "$files" | xargs grep -nE '/Users/[a-z]|/home/[a-z]' 2>/dev/null); then
  echo "ABSOLUTE HOME PATHS:"; echo "$hits"; fail=1
fi
# 2. Credential-shaped URLs (user:pass@host)
if hits=$(echo "$files" | xargs grep -nE '[a-z]+://[^ /:]+:[^ /@]+@[a-zA-Z0-9.-]+' 2>/dev/null); then
  echo "CREDENTIAL-SHAPED URLS:"; echo "$hits"; fail=1
fi
# 3. UUID-shaped session/trace ids
if hits=$(echo "$files" | xargs grep -nE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' 2>/dev/null); then
  echo "UUID-SHAPED IDS:"; echo "$hits"; fail=1
fi
[ "$fail" -eq 0 ] && echo "clean"

echo "== private term blocklist =="
terms_file="scripts/leak-terms.local.txt"
if [ ! -f "$terms_file" ]; then
  echo "WARN: $terms_file not found — structural checks only. Create it (gitignored) with your private terms."
else
  while IFS=$'\t' read -r term allow; do
    [ -z "$term" ] && continue; case "$term" in \#*) continue;; esac
    scan="$files"
    if [ -n "${allow:-}" ]; then
      IFS=',' read -ra _allowed <<< "${allow#ALLOW:}"
      for _p in "${_allowed[@]}"; do scan=$(echo "$scan" | grep -v "^${_p}$" || true); done
    fi
    if hits=$(echo "$scan" | xargs grep -inl -- "$term" 2>/dev/null); then
      echo "TERM '$term' FOUND IN:"; echo "$hits"; fail=1
    fi
  done < "$terms_file"
  [ "$fail" -eq 0 ] && echo "clean"
fi

echo "== commit messages =="
if [ -f "$terms_file" ]; then
  while IFS=$'\t' read -r term _; do
    [ -z "$term" ] && continue; case "$term" in \#*) continue;; esac
    if git log --all --format='%H %s %b' | grep -iq -- "$term"; then
      echo "TERM '$term' IN COMMIT HISTORY:"; git log --all --oneline -i --grep="$term"; fail=1
    fi
  done < "$terms_file"
fi
[ "$fail" -eq 0 ] && echo "clean"

if [ "$fail" -eq 0 ]; then echo "LEAK-CHECK: PASS"; else echo "LEAK-CHECK: FAIL"; exit 1; fi
