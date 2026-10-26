#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ! -f .venv/bin/python ]]; then
  printf '%s\n' 'Run: python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt'
  exit 1
fi
exec .venv/bin/python main.py "$@"
