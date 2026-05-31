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

# -f: silent if the file does not exist (idempotent)
rm -f "$FLAG"
