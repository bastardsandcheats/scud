#!/usr/bin/env bash
set -euo pipefail
DEST="${SCUD_HOME:-/opt/scud}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ $EUID -ne 0 ]]; then echo "Run as root: sudo ./install.sh" >&2; exit 1; fi
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
if ! python3 -m venv --help >/dev/null 2>&1; then
  apt-get update && apt-get install -y python3-venv
fi
if ! command -v ffprobe >/dev/null 2>&1; then
  if command -v apt-get >/dev/null; then apt-get update && apt-get install -y ffmpeg; else echo "Install ffprobe/ffmpeg first" >&2; exit 1; fi
fi
# Stop before replacing modules or the Python environment.
systemctl stop scud 2>/dev/null || true
mkdir -p "$DEST"
SRC_REAL="$(readlink -f "$SOURCE_DIR")"
DST_REAL="$(readlink -m "$DEST")"
if [[ "$SRC_REAL" != "$DST_REAL" ]]; then
  # Operator state and Git metadata never travel with a code update.
  tar -C "$SOURCE_DIR" --exclude='./.git' --exclude='./.gitignore' \
      --exclude='./venv' --exclude='./.venv' --exclude='./data' --exclude='./logs' \
      --exclude='./config.yml' --exclude='./release-compat.sh' -cf - . | tar -C "$DEST" -xf -
fi
rm -rf "$DEST/venv" "$DEST/__pycache__"
python3 -m venv "$DEST/venv"
"$DEST/venv/bin/pip" install --upgrade pip wheel
"$DEST/venv/bin/pip" install -r "$DEST/requirements.txt"
mkdir -p "$DEST/data"; chmod 700 "$DEST/data"
# Release Scud's own listener when updating an existing installation.
systemctl stop scud 2>/dev/null || true
PORT="${SCUD_PORT:-}"
while true; do
  if SELECTED_PORT=$(PYTHONPATH="$DEST" "$DEST/venv/bin/python" "$DEST/scripts/install_port.py" "$DEST/config.yml" "$PORT"); then
    PORT="$SELECTED_PORT"
    break
  else
    result=$?
    [[ $result -eq 2 ]] || exit "$result"
  fi
  if ! read -r -p "Select another Scud port (1-65535): " PORT; then
    echo "No port selected. Run again with SCUD_PORT=<available-port> ./install.sh" >&2
    exit 1
  fi
done
cat >/etc/systemd/system/scud.service <<EOF
[Unit]
Description=Scud local media source for Rex
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$DEST
ExecStart=$DEST/venv/bin/python -m scud --config $DEST/config.yml
Restart=on-failure
RestartSec=3
UMask=0077
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now scud
PYTHONPATH="$DEST" "$DEST/venv/bin/python" - "$DEST/config.yml" <<'PY'
import sys, time, urllib.request
from pathlib import Path
from scud.config import load_config
cfg = load_config(Path(sys.argv[1]))
host = cfg['host']
if host == '0.0.0.0':
    host = '127.0.0.1'
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
for attempt in range(20):
    try:
        with opener.open(f"http://{host}:{cfg['port']}/", timeout=1) as response:
            if response.status == 200:
                break
    except OSError:
        pass
    time.sleep(0.5)
else:
    sys.exit('Scud did not become ready. Check: journalctl -u scud -n 50')
PY
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "Scud installed in $DEST"
echo "Open: http://${IP:-127.0.0.1}:$PORT/"
echo "Logs: journalctl -u scud -f"
echo "Status: systemctl status scud"
