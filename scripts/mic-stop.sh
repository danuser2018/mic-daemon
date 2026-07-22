#!/usr/bin/env bash
# mic-stop.sh — Remove the recording flag (push-to-talk: key release).
#
# Uso:
#   mic-stop
#
# Vinculación a hotkey recomendada (sxhkd, push-to-talk — KeyRelease):
#   @super + F10
#       mic-stop

set -euo pipefail

FLAG="/tmp/voice_assistant/recording.flag"

# 1. Non-blocking novactl invocation
if command -v novactl >/dev/null 2>&1; then
    novactl stop-capture || echo "Warning: novactl stop-capture failed" >&2
else
    echo "Warning: novactl is not installed or not in PATH" >&2
fi

# 2. Legacy flag management for backward compatibility
# -f: silent if the file does not exist (idempotent)
rm -f "$FLAG"
