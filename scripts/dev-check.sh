#!/usr/bin/env bash
# One call, ~3 lines of output. Replaces running pytest/ruff/black/smoke
# as four separate commands that each echo their own banner.
#
#   scripts/dev-check.sh          verify only
#   scripts/dev-check.sh --fmt    format first, then verify
#
# --fmt is separate on purpose: formatting rewrites files, and rewriting a
# file an agent has already read forces its whole contents back into context.
# Format once, at the end, right before commit.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
if [ "${1:-}" = "--fmt" ]; then
  black bunkervm/ -q 2>/dev/null
fi

t=$(python -m pytest tests/test_features.py tests/test_imports.py -q 2>&1 | tail -1)
echo "tests : $t"
case "$t" in *fail*|*error*) fail=1 ;; esac

r=$(ruff check bunkervm/ 2>&1 | tail -1)
echo "ruff  : $r"
case "$r" in *"All checks passed"*) ;; *) fail=1 ;; esac

b=$(black --check bunkervm/ 2>&1 | tail -1)
echo "black : $b"
case "$b" in *"would be reformatted"*) fail=1 ;; esac

if bunkervm demo --local >/dev/null 2>&1; then
  echo "smoke : demo --local ok"
else
  echo "smoke : demo --local FAILED"
  fail=1
fi

echo "version: $(python -c 'import bunkervm;print(bunkervm.__version__)' 2>/dev/null)"
exit $fail
