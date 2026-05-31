#!/usr/bin/env bash
# mic-toggle.sh — Toggle recording flag (create if absent, delete if present).
#
# Uso:
#   mic-toggle
#
# Vinculación a hotkey recomendada (sxhkd):
#   super + F9
#       mic-toggle

set -euo pipefail

FLAG="/tmp/voice_assistant/recording.flag"
FLAG_DIR="$(dirname "$FLAG")"

# Ensure the directory exists before any file operation
mkdir -p "$FLAG_DIR"

if [ -f "$FLAG" ]; then
    rm "$FLAG"
else
    touch "$FLAG"
fi
