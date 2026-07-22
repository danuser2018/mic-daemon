#!/usr/bin/env bash
# mic-start.sh — Trigger speech capture start via novactl.

set -euo pipefail

if command -v novactl >/dev/null 2>&1; then
    exec novactl start-capture
else
    echo "Error: novactl is not installed or not in PATH" >&2
    exit 1
fi
