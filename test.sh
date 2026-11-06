#!/usr/bin/env bash
# Run the test suite.  Extra arguments are passed through, e.g. ./test.sh -v
set -euo pipefail

# tests write to tests/tmp/..., so they must run from the repo root
cd "$(dirname "$0")"

PYTHON=python
if [ -x .venv/bin/python ]; then
    PYTHON=.venv/bin/python
fi

exec "$PYTHON" -m unittest discover -s tests "$@"
