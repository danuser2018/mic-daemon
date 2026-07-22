#!/usr/bin/env bash
# mic-toggle.sh — Toggle speech capture via novactl.

set -euo pipefail

TOGGLE_STATE_FILE="/tmp/mic_toggle_active"

if command -v novactl >/dev/null 2>&1; then
    if [ -f "$TOGGLE_STATE_FILE" ]; then
        rm -f "$TOGGLE_STATE_FILE"
        exec novactl stop-capture
    else
        touch "$TOGGLE_STATE_FILE"
        exec novactl start-capture
    fi
else
    echo "Error: novactl is not installed or not in PATH" >&2
    exit 1
fi
