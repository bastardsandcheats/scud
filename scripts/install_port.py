"""Validate the install port and persist it only after a successful bind."""
import socket
import sys
from pathlib import Path

from scud.config import load_config, save_config


def main():
    path = Path(sys.argv[1])
    cfg = load_config(path)
    candidate = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else cfg["port"]
    try:
        port = int(candidate)
        if not 1 <= port <= 65535:
            raise ValueError
    except (ValueError, TypeError):
        print("Select a valid port between 1 and 65535.", file=sys.stderr)
        return 2
    host = cfg["host"]
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
    except OSError as exc:
        print(f"Cannot use {host}:{port}: {exc}. Select another port.", file=sys.stderr)
        return 2
    cfg["port"] = port
    save_config(path, cfg)
    print(port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
