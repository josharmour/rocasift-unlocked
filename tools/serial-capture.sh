#!/usr/bin/env bash
# Capture the Sifter's UART console (JRIP1 header) via USB serial adapter.
# Usage: ./serial-capture.sh [device] [baud] [seconds]
#   device defaults to first /dev/tty.usbserial* or /dev/tty.usb* on macOS
#   baud defaults to 115200 (verified 115200 8N1, 3.3V logic on JRIP1)
# Wiring: adapter GND -> JRIP1 pin 4 (ground), adapter RXD -> JRIP1 pin 2 (UART0 TX).
#         NEVER connect adapter VCC to the board. See HANDOFF-UART.md for pinout details.
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
