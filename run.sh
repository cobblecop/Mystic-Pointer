#!/usr/bin/env bash
# Start Mystic Pointer with the project's virtual environment.
#
#   ./run.sh              start in the system tray
#   ./run.sh --activate   open the overlay immediately
#
# Set up the environment first with:
#   python3 -m venv .venv
#   .venv/bin/pip install -r requirements.txt
set -euo pipefail
cd "$(dirname "$0")"
exec .venv/bin/python main.py "$@"
