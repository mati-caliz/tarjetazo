#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
set -a
source .env
[ -r .env.respondi ] && source .env.respondi
set +a

SHARED_LLM_ENV="${SHARED_LLM_ENV:-../respondi/.env}"
if [ -r "$SHARED_LLM_ENV" ]; then
  while IFS= read -r line; do
    case "$line" in
      DEEPSEEK_API_KEY=*|DEEPSEEK_BASE_URL=*|GEMINI_API_KEY=*|GEMINI_BASE_URL=*)
        key="${line%%=*}"
        [ -n "${!key:-}" ] || export "$line"
        ;;
    esac
  done < "$SHARED_LLM_ENV"
fi

venv/bin/python3 src/main.py "$@"
