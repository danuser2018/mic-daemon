#!/usr/bin/env bash
# mic-stop.sh — Trigger speech capture stop via novactl.

set -euo pipefail

if command -v novactl >/dev/null 2>&1; then
    exec novactl stop-capture
else
    echo "Error: novactl is not installed or not in PATH" >&2
    exit 1
fi
