#!/usr/bin/env bash
# Start Rackoon. Creates the virtualenv on first run.
#   RACKOON_HOST     interface to listen on (default 0.0.0.0 = whole LAN)
#   RACKOON_PORT     port (default 8080)
#   RACKOON_DATA_DIR where config.json and history.db live (default ~/.local/share/rackoon)
#   RACKOON_SSL_CERT / RACKOON_SSL_KEY  serve over HTTPS with this certificate and key
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/uvicorn ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
TLS=()
[ -n "$RACKOON_SSL_CERT" ] && TLS=(--ssl-certfile "$RACKOON_SSL_CERT" --ssl-keyfile "$RACKOON_SSL_KEY")
exec .venv/bin/uvicorn app.main:app --host "${RACKOON_HOST:-0.0.0.0}" --port "${RACKOON_PORT:-8080}" "${TLS[@]}"
