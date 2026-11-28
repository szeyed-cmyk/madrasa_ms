#!/usr/bin/env bash
# Madrasa & School Admin System - Linux / macOS starter.
# Run from anywhere:  ./start.sh   (or: bash start.sh)
# On the first start: creates the "venv" folder and installs the pinned packages.
# See HowToSetup.md, section 3.
# The login page shows Demo sign-in accounts by default. For a real school set DEMO_LOGINS=false.
# For a sample school that resets on every start, run ./start-demo.sh instead.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if [ ! -x venv/bin/python ]; then
  if ! command -v "$PY" >/dev/null 2>&1; then
    echo "python3 was not found. Install Python 3.11 or newer (e.g. sudo apt install python3 python3-venv)." >&2
    exit 1
  fi
  echo "Creating the virtual environment ..."
  "$PY" -m venv venv
fi

if ! venv/bin/python -c "import uvicorn, fastapi, sqlalchemy" 2>/dev/null; then
  echo "Installing the pinned packages from requirements.lock ..."
  venv/bin/python -m pip install --disable-pip-version-check --require-hashes -r requirements.lock
fi

exec venv/bin/python main.py
