#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
set -a
source .env
set +a
venv/bin/python3 src/main.py
