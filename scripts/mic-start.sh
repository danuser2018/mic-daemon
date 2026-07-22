#!/usr/bin/env bash
# mic-start.sh — Create the recording flag (push-to-talk: key press).
#
# Uso:
#   mic-start
#
# Vinculación a hotkey recomendada (sxhkd, push-to-talk):
#   super + F10
#       mic-start

set -euo pipefail

FLAG="/tmp/voice_assistant/recording.flag"

# 1. Non-blocking novactl invocation
if command -v novactl >/dev/null 2>&1; then
    novactl start-capture || echo "Warning: novactl start-capture failed" >&2
else
    echo "Warning: novactl is not installed or not in PATH" >&2
fi

# 2. Legacy flag management for backward compatibility
mkdir -p "$(dirname "$FLAG")"
touch "$FLAG"
