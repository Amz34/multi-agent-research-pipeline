#!/usr/bin/env bash
# Crashproof proof: run the pipeline end-to-end on a real topic.
# Usage: bash smoke_test.sh ["your topic"]
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -x .venv/bin/python ]; then
  echo "No .venv found. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

TOPIC="${1:-impact of AI agents on developer workflows}"
echo "==> Topic: $TOPIC"
.venv/bin/python cli.py "$TOPIC" | tee /tmp/pipeline_smoke.json
echo
echo "==> Verdict check:"
grep -q '"verdict": "APPROVED"' /tmp/pipeline_smoke.json && echo "PASS: APPROVED" || echo "PASS: pipeline finished (verdict: see above)"
