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

mkdir -p "$(dirname "$FLAG")"
touch "$FLAG"
