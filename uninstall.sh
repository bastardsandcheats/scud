#!/usr/bin/env bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Run as root" >&2; exit 1; fi
systemctl disable --now scud 2>/dev/null || true
rm -f /etc/systemd/system/scud.service
systemctl daemon-reload
echo "Scud service removed. Files, configuration, and data remain in /opt/scud."
