#!/usr/bin/env bash
# Public demo starter for Linux / macOS.
# Run from the "Madrasa Admin Project" folder:  ./start-demo.sh
# Then open http://localhost:8000 — landing page, Live Demo, Take the tour.
# For a real school install, use ./start.sh instead.
set -euo pipefail
cd "$(dirname "$0")"
export DEMO_MODE=true
export SEED_DEMO_DATA=true
exec ./start.sh
