#!/usr/bin/env bash
# Start Server Manager. Creates the virtualenv on first run.
#   SM_HOST     interface to listen on (default 0.0.0.0 = whole LAN)
#   SM_PORT     port (default 8080)
#   SM_DATA_DIR where config.json and history.db live (default ./data)
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/uvicorn ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/uvicorn app.main:app --host "${SM_HOST:-0.0.0.0}" --port "${SM_PORT:-8080}"
