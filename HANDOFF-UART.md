# UART SESSION HANDOFF — read me first (2026-10-24)

UPDATE 2026-10-28: hunt CLOSED — JPRG1 is not a debug UART. Adapter chain was
proven good (loopback echo + GND-hold zeros); boot captures on pins 1/4/5 at
115200/57600 all zero bytes; DMM survey shows pins 1,2,4,5 idle ~3.9 V, pin 6
~0.5 V, pin 3 GND → programming-bus signature (I2C/SPI), not async console.
Full write-up: FINDINGS.md §10d. Next leads: JRESET pads, test points, FCC ID
internal photos. Cold ground joint on pin 3 was found and resoldered this
session; scope observations from before that fix are unreliable.

Session moved from <HOST> to <HOST> (USB-TTL adapter is plugged in HERE).

State:
- JPRG1 header soldered on mainboard 10U9020 REV 4. Pin 1 = UART TX candidate
  (scope: TTL, idles ~3.3V, boot bursts). Pin 3 = GND (continuity-verified).
- Adapter: 5-pin USB-TTL (3V3/5V/GND/TXD/RXD). Wired: RXD→JPRG1 pin 1,
  GND→JPRG1 pin 3. VCC/3V3/5V/TXD unconnected. NEVER connect VCC.
- Baud UNKNOWN: scope decode at 115200 gave frame errors only.

Next steps (on <HOST>):
1. ls /dev/ttyUSB* (or ttyACM*) to find the port.
2. Stepped-baud boot capture: for baud in 115200 57600 9600 — stty -F <dev>
   $baud cs8 -cstopb -parenb raw; capture to device/uart/boot-<baud>.log while
   <NAME> power-cycles the Sifter. Look for readable text.
3. All garbage → move RXD to pins 2/4/5/6 one at a time (power cycle each).
4. Readable output → try keypress during U-Boot countdown for a prompt.
5. Log everything into device/uart/ and update the skill notes.

Full context: roca-sifter-re skill + references/uart-bringup.md +
BOARD-NOTES.md in this folder.
