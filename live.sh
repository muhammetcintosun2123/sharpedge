#!/usr/bin/env bash
# SharpEdge — start the genuinely-live server + a public tunnel URL you can open anywhere.
# Usage: bash live.sh          (needs the venv with httpx+solders and the activated token)
set -e
PORT="${PORT:-8787}"
PY="${PY:-$HOME/leadgen/.venv/bin/python}"
echo "starting SharpEdge live server on :$PORT (polls the real TxLINE feed)…"
setsid bash -c "$PY serve.py --port $PORT --live >/tmp/sharpedge_live.log 2>&1 < /dev/null" &
sleep 3
echo "opening a public tunnel (npx localtunnel)…"
echo "→ when it prints 'your url is https://xxxx.loca.lt', open that link in any browser."
echo "  (loca.lt may show a one-time 'Click to Continue' page — click it once.)"
npx --yes localtunnel --port "$PORT"
