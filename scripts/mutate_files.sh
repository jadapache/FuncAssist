#!/bin/bash
# Mutation testing for backend files, running only the tests that mention each file.
#
# Usage (from backend/):  ../scripts/mutate_files.sh app/path/one.py app/path/two.py
#
# Needs `mutator` on the PATH (Windows cannot create the symlinks it uses: run it in WSL or Linux) and
# coverage already written to target/coverage/python/lcov.info:
#   python -m coverage run --source=app -m pytest tests
#   python -m coverage lcov -o target/coverage/python/lcov.info
#
# Environment:
#   PYTHON   interpreter that has the backend dependencies (default: python)
#   WORKERS  mutants run at once (default: 6)
#   OUT      directory for one log per file and summary.txt (default: .metrics/mutate-logs)
set -u

PYTHON=${PYTHON:-python}
WORKERS=${WORKERS:-6}
OUT=${OUT:-.metrics/mutate-logs}
mkdir -p "$OUT"
: > "$OUT/summary.txt"

if [ $# -eq 0 ]; then
  echo "usage: $0 <file.py>..." >&2
  exit 2
fi

# Tests that import the module, or else any test that names it.
tests_for() {
  local file=$1 module parent base found
  module=$(echo "${file%.py}" | tr / .)
  parent=${module%.*}
  base=$(basename "${file%.py}")
  found=$(grep -lE "${module}\b|from ${parent} import .*\b${base}\b" tests/*.py 2>/dev/null | tr '\n' ' ')
  [ -z "$found" ] && found=$(grep -lwE "${base}" tests/*.py 2>/dev/null | tr '\n' ' ')
  echo "$found"
}

status=0
for file in "$@"; do
  tests=$(tests_for "$file")
  if [ -z "$tests" ]; then
    echo "NOTESTS $file" | tee -a "$OUT/summary.txt"
    status=1
    continue
  fi
  log="$OUT/$(echo "$file" | tr / _).log"
  mutator --reuse-coverage --mutate-all --max-workers "$WORKERS" \
    --test-command "$PYTHON -m pytest $tests -q -x --no-cov -p no:cacheprovider" "$file" > "$log" 2>&1
  total=$(grep -E '^Total' "$log" | awk '{print "killed="$(NF-4)" survived="$(NF-3)" uncovered="$(NF-2)" sites="$(NF-1)" score="$NF}')
  echo "$file ${total:-FAILED}" | tee -a "$OUT/summary.txt"
  grep -E '^(SURVIVED|UNCOVERED)' "$log" | sed 's/^/  /'
  case "$total" in *"survived=0 uncovered=0"*) ;; *) status=1 ;; esac
done
exit $status
