#!/usr/bin/env bash
# Capture the Sifter's UART console (JPRG1 header) via USB serial adapter.
# Usage: ./serial-capture.sh [device] [baud] [seconds]
#   device defaults to first /dev/tty.usbserial* or /dev/tty.usb* on macOS
#   baud defaults to 115200 (try 57600, 9600 if garbage)
# Wiring: adapter GND -> JPRG1 pin 3 (ground), adapter RX -> candidate TX pin.
#         NEVER connect adapter VCC to the board.
set -euo pipefail

DEV="${1:-}"
BAUD="${2:-115200}"
SECS="${3:-60}"

if [[ -z "$DEV" ]]; then
  DEV=$(ls /dev/tty.usbserial* /dev/tty.usb* 2>/dev/null | head -1 || true)
fi
[[ -n "$DEV" ]] || { echo "no USB serial device found"; exit 1; }
echo "capturing $DEV @ $BAUD for ${SECS}s — power-cycle the Sifter NOW"
OUT="device/usb/uart-console-$(date +%Y%m%d-%H%M%S)-${BAUD}.log"
mkdir -p "$(dirname "$OUT")"
# -u unbuffered; raw 8N1 via stty
stty -f "$DEV" "$BAUD" cs8 -cstopb -parenb raw >/dev/null 2>&1 || \
  stty -F "$DEV" "$BAUD" cs8 -cstopb -parenb raw >/dev/null 2>&1 || true
timeout "$SECS" cat "$DEV" | tee "$OUT" || true
echo "saved: $OUT ($(wc -c < "$OUT") bytes)"
