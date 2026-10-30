#!/usr/bin/env python3
"""Capture the Sifter's live event bus.

Two unauthenticated channels carry the same MessagePack stream:

  21587  raw TCP, server speaks first
  9002   WebSocket, handshake succeeds on any path

Usage:
  SIFTER_HOST=192.168.1.50 python3 tools/bus-probe.py 30
  python3 tools/bus-probe.py 30 --host 192.168.1.50 --out /tmp/bus.jsonl

Prints each decoded message, flags anything that looks like an image reference,
and summarises event and node counts at the end. Read-only: nothing is sent to
the device beyond the WebSocket handshake.
"""
import argparse, base64, json, os, socket, struct, sys, threading, time
from collections import Counter


class Unpacker:
    """Minimal MessagePack decoder (no third-party dependency)."""

    def __init__(self, buf):
        self.b = buf
        self.i = 0

    def need(self, n):
        if self.i + n > len(self.b):
            raise EOFError

    def u8(self):
        self.need(1)
        v = self.b[self.i]
        self.i += 1
        return v

    def take(self, n):
        self.need(n)
        v = self.b[self.i:self.i + n]
        self.i += n
        return v

    def unpack(self):
        c = self.u8()
        if c <= 0x7F:
            return c
        if c >= 0xE0:
            return c - 256
        if 0x80 <= c <= 0x8F:
            return {self.unpack(): self.unpack() for _ in range(c & 0x0F)}
        if 0x90 <= c <= 0x9F:
            return [self.unpack() for _ in range(c & 0x0F)]
        if 0xA0 <= c <= 0xBF:
            return self.take(c & 0x1F).decode("utf-8", "replace")
        if c == 0xC0:
            return None
        if c == 0xC2:
            return False
        if c == 0xC3:
            return True
        if c == 0xC4:
            return self.take(self.u8())
        if c == 0xC5:
            return self.take(struct.unpack(">H", self.take(2))[0])
        if c == 0xC6:
            return self.take(struct.unpack(">I", self.take(4))[0])
        if c == 0xCA:
            return struct.unpack(">f", self.take(4))[0]
        if c == 0xCB:
            return struct.unpack(">d", self.take(8))[0]
        if c == 0xCC:
            return self.u8()
        if c == 0xCD:
            return struct.unpack(">H", self.take(2))[0]
        if c == 0xCE:
            return struct.unpack(">I", self.take(4))[0]
        if c == 0xCF:
            return struct.unpack(">Q", self.take(8))[0]
        if c == 0xD0:
            return struct.unpack(">b", self.take(1))[0]
        if c == 0xD1:
            return struct.unpack(">h", self.take(2))[0]
        if c == 0xD2:
            return struct.unpack(">i", self.take(4))[0]
        if c == 0xD3:
            return struct.unpack(">q", self.take(8))[0]
        if c == 0xD9:
            return self.take(self.u8()).decode("utf-8", "replace")
        if c == 0xDA:
            return self.take(struct.unpack(">H", self.take(2))[0]).decode("utf-8", "replace")
        if c == 0xDB:
            return self.take(struct.unpack(">I", self.take(4))[0]).decode("utf-8", "replace")
        if c == 0xDC:
            return [self.unpack() for _ in range(struct.unpack(">H", self.take(2))[0])]
        if c == 0xDD:
            return [self.unpack() for _ in range(struct.unpack(">I", self.take(4))[0])]
        if c == 0xDE:
            n = struct.unpack(">H", self.take(2))[0]
            return {self.unpack(): self.unpack() for _ in range(n)}
        if c == 0xDF:
            n = struct.unpack(">I", self.take(4))[0]
            return {self.unpack(): self.unpack() for _ in range(n)}
        raise ValueError(f"unhandled msgpack byte {c:#04x}")


IMAGE_HINTS = ("image", "jpeg", "jpg", "png", "frame", "camera", "photo",
               "path", "url", "uri", "blob", "base64", "file")


def walk(obj, path=""):
    """Yield (path, value) leaves."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, obj


def report(tag, obj):
    hits = []
    for p, v in walk(obj):
        low = p.lower()
        if isinstance(v, bytes) and len(v) > 64:
            hits.append((p, f"<binary {len(v)} bytes>"))
        elif isinstance(v, str) and len(v) > 40 and any(h in low for h in IMAGE_HINTS):
            hits.append((p, v[:120]))
    print(f"[{tag}] {type(obj).__name__}: {str(obj)[:300]}")
    for p, v in hits:
        print(f"   !! IMAGE-CANDIDATE {p} = {v}")


def raw_stream(host, secs, sink):
    s = socket.create_connection((host, 21587), timeout=5)
    s.settimeout(secs)
    buf = b""
    t_end = time.time() + secs
    while time.time() < t_end:
        try:
            d = s.recv(65536)
            if not d:
                break
            buf += d
        except socket.timeout:
            break
        while True:
            u = Unpacker(buf)
            try:
                obj = u.unpack()
            except EOFError:
                break
            except Exception as e:
                print("[21587] decode error:", e)
                buf = b""
                break
            buf = buf[u.i:]
            sink.append({"channel": "21587", "msg": obj})
            report("21587", obj)
    s.close()


def ws_connect(host, path="/"):
    s = socket.create_connection((host, 9002), timeout=5)
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}:9002\r\nUpgrade: websocket\r\n"
               f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
               f"Sec-WebSocket-Version: 13\r\n\r\n").encode())
    hdr = b""
    while b"\r\n\r\n" not in hdr:
        hdr += s.recv(1)
    assert b"101" in hdr.split(b"\r\n")[0], hdr[:100]
    return s


def recv_exact(s, n):
    out = b""
    while len(out) < n:
        d = s.recv(n - len(out))
        if not d:
            raise EOFError
        out += d
    return out


def ws_stream(host, secs, sink):
    s = ws_connect(host)
    s.settimeout(secs)
    t_end = time.time() + secs
    while time.time() < t_end:
        try:
            h = recv_exact(s, 2)
        except socket.timeout:
            break
        opcode = h[0] & 0x0F
        masked = h[1] & 0x80
        ln = h[1] & 0x7F
        if ln == 126:
            ln = struct.unpack(">H", recv_exact(s, 2))[0]
        elif ln == 127:
            ln = struct.unpack(">Q", recv_exact(s, 8))[0]
        mask = recv_exact(s, 4) if masked else None
        payload = recv_exact(s, ln)
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        print(f"[9002] frame opcode={opcode} len={ln}")
        try:
            obj = Unpacker(payload).unpack()
            sink.append({"channel": "9002", "msg": obj})
            report("9002", obj)
        except Exception as e:
            print(f"[9002] non-msgpack payload ({e}): {payload[:120]!r}")
    s.close()


def summarise(sink):
    events = Counter()
    nodes = Counter()
    for rec in sink:
        m = rec["msg"]
        if isinstance(m, list) and len(m) >= 3 and isinstance(m[1], str):
            events[(rec["channel"], m[1])] += 1
            for item in m[2]:
                if isinstance(item, dict):
                    for k in item:
                        nodes[k.split("/")[0]] += 1
    print("\n== summary ==")
    print("messages:", len(sink))
    for (ch, ev), n in sorted(events.items()):
        print(f"  {ch} {ev}: {n}")
    print("node types:", dict(nodes))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("seconds", nargs="?", type=int, default=30,
                    help="capture duration (default 30)")
    ap.add_argument("--host", default=os.environ.get("SIFTER_HOST", ""),
                    help="device address; defaults to $SIFTER_HOST")
    ap.add_argument("--out", help="write decoded messages as JSON lines")
    args = ap.parse_args()

    host = args.host.replace("https://", "").replace("http://", "").rstrip("/")
    if not host:
        sys.exit("set SIFTER_HOST or pass --host")

    sink = []
    t1 = threading.Thread(target=raw_stream, args=(host, args.seconds, sink))
    t2 = threading.Thread(target=ws_stream,
                          args=(host, max(args.seconds - 5, args.seconds), sink))
    t1.start(); t2.start()
    t1.join(); t2.join()

    summarise(sink)
    if args.out:
        with open(args.out, "w") as fh:
            for rec in sink:
                fh.write(json.dumps(rec,
                                    default=lambda o: f"<binary {len(o)} bytes>") + "\n")
        print(f"\nwrote {len(sink)} messages to {args.out}")


if __name__ == "__main__":
    main()
