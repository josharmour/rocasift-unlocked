#!/usr/bin/env python3
"""Passive usbmon sniffer for Linux - watches ALL traffic on a USB bus without
claiming anything (complements usb-probe.py's per-interface claims).

Header size varies by kernel series: classic docs describe 64 bytes (ending
with interval/start_frame/xfer_flags/ndesc); several kernels emit 48 bytes
(ending after the setup/iso union) - verified by raw od on x86_64 omarchy
2026-10-27. Auto-detected here; force with --header-bytes.

Drain via nonblocking reads + short sleep; do not gate on select/poll.

Usage: sudo ./usbmon-sniff.py --bus N [--dev DEVNUM] [--seconds S] [--out FILE]
Requires root and `modprobe usbmon`.
"""
import argparse
import os
import struct
import sys
import time

FMT48 = "<QBBBBHbbqiiII8s"
FMT64 = FMT48 + "iiII"
TYPES = {83: "SUBMIT", 67: "CALLBACK", 69: "ERROR"}   # 'S', 'C', 'E'
XFER = {0: "ISO", 1: "INTR", 2: "CTRL", 3: "BULK"}
FLAG_CAPTURED = 60                                    # '<'


def read_chunk(fd):
    try:
        return os.read(fd, 65536)
    except BlockingIOError:
        return b""


def pick_stride(buf):
    """Score type-byte validity along each candidate stride; None if tied."""
    scores = {}
    for size in (48, struct.calcsize(FMT64)):
        ok = tot = off = 0
        while off + size <= len(buf) and tot < 32:
            t_byte = buf[off + 8]
            cap_len = int.from_bytes(buf[off + 36:off + 40], "little")
            tot += 1
            if t_byte in TYPES and cap_len <= 65536:
                ok += 1
            off += size + cap_len
        if tot:
            scores[size] = ok / tot
    if not scores:
        return None
    best_val = max(scores.values())
    winners = [s for s, v in scores.items() if v == best_val]
    return winners[0] if len(winners) == 1 else None


def main():
    ap = argparse.ArgumentParser(description="passive usbmon bus sniffer")
    ap.add_argument("--bus", type=int, default=1)
    ap.add_argument("--dev", type=int, default=0,
                    help="only show this bus-local device number; 0=all")
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--out", default="-", help="'-' for stdout or a file path")
    ap.add_argument("--header-bytes", type=int, choices=(48, 64), default=None,
                    help="force header size instead of auto-detect")
    args = ap.parse_args()

    fd = os.open("/dev/usbmon%d" % args.bus, os.O_RDONLY | os.O_NONBLOCK)
    out = sys.stdout if args.out == "-" else open(args.out, "w")
    end = time.time() + args.seconds
    grace_end = end + 5
    stride = args.header_bytes
    buf = b""
    n_read = n_shown = n_resync = 0

    def drain_pending():
        """Parse complete events currently in buf; leave partial tail."""
        nonlocal buf, n_read, n_shown, n_resync
        size = stride
        while len(buf) >= size:
            t_byte = buf[8]
            cap_len = int.from_bytes(buf[36:40], "little")
            if t_byte not in TYPES or cap_len > 65536:
                buf = buf[1:]          # lost sync; slide one byte
                n_resync += 1
                continue
            if len(buf) < size + cap_len:
                break                  # wait for payload bytes
            hdr, rest = buf[:size], buf[size:]
            f = struct.unpack(FMT48 if size == struct.calcsize(FMT48) else FMT64,
                              hdr)
            data_len = min(cap_len, len(rest))
            data = rest[:data_len]
            buf = rest[data_len:]
            n_read += 1
            t_type, xfer, epnum, devnum = f[1], f[2], f[3], f[4]
            if args.dev and devnum != args.dev:
                continue
            n_shown += 1
            ts = "%.6f" % (f[8] + f[9] / 1e6)
            dirn = "IN" if epnum & 0x80 else "OUT"
            out.write(
                "[%s] %-8s %-5s ep%-2d%-4s dev%d len=%-6d cap=%-6d st=%d\n"
                % (ts[-14:], TYPES.get(t_type, "?"),
                   XFER.get(xfer, str(xfer)), epnum & 0x7F, dirn.ljust(3),
                   devnum, f[11], cap_len, f[10]))
            if t_type == ord("S") and xfer == 2 and f[6] == FLAG_CAPTURED:
                out.write("    setup(8): %s\n" % f[13].hex())
            if f[7] == FLAG_CAPTURED and data:
                out.write("    data(%d): %s\n" % (len(data), data.hex()))
            out.flush()

    try:
        while True:
            now = time.time()
            if now >= grace_end:
                break
            chunk = read_chunk(fd)
            if chunk:
                buf += chunk
            elif now < end:
                time.sleep(0.05)
                continue
            elif not buf:
                break
            if stride is None:
                if len(buf) >= 128 or now >= end:
                    stride = pick_stride(buf) or struct.calcsize(FMT48)
                    print("# usbmon header auto-detected: %d bytes"
                          % stride, file=sys.stderr)
                else:
                    continue
            drain_pending()
        drain_pending()
    finally:
        print("# events read=%d shown=%d resyncs=%d header=%s"
              % (n_read, n_shown, n_resync,
                 stride if stride else "undetected"), file=sys.stderr)


if __name__ == "__main__":
    main()
