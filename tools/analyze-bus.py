#!/usr/bin/env python3
"""Offline lifecycle analysis for captured Sifter event-bus traffic.

Reads JSONL produced by tools/bus-probe.py or the live captures under
device/. It never opens a network connection.

Accepted line shapes:
  [2, "nodeChanged", [{"PageQueue": {"41": {"Front": {"state": "Safe"}}}}]]
  {"channel": "21587", "msg": [...]}
  {"utc": "2026-10-31T05:58:33.628932+00:00", "msg": [...]}

The analyser groups records into *segments*. A segment starts when the
timestamp gap exceeds --session-gap or when a PageQueue id goes backwards.
Page ids are not globally unique: they reset after a pause or a new job, so a
page is identified by (segment, page_id), never by page_id alone.

Usage:
  python3 tools/analyze-bus.py device/research/live-sifter-20261031/events-continuation.jsonl
  python3 tools/analyze-bus.py device/bus-capture-20261030c.jsonl --csv /tmp/pages.csv
  python3 tools/analyze-bus.py device/*.jsonl --json /tmp/lifecycle.json

Output is descriptive only. It does not prove where image bytes live, whether
an upload succeeded, or that a handle remains valid after nodeRemoved.
"""
import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime


def parse_utc(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class Record:
    __slots__ = ("idx", "utc", "channel", "event", "payload")

    def __init__(self, idx, utc, channel, event, payload):
        self.idx = idx
        self.utc = utc
        self.channel = channel
        self.event = event
        self.payload = payload


class Side:
    __slots__ = ("scanning", "safe", "image", "ejected", "descriptor")

    def __init__(self):
        self.scanning = None
        self.safe = None
        self.image = None
        self.ejected = None
        self.descriptor = None


class Page:
    __slots__ = ("segment", "page_id", "added", "removed", "first", "last",
                 "sides", "foil")

    def __init__(self, segment, page_id):
        self.segment = segment
        self.page_id = page_id
        self.added = None
        self.removed = None
        self.first = None
        self.last = None
        self.sides = {"Front": Side(), "Back": Side()}
        self.foil = None


def load(path):
    records = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"{path}:{lineno}: skipped invalid JSON ({exc})",
                      file=sys.stderr)
                continue

            if isinstance(obj, list):
                msg, utc, channel = obj, None, None
            elif isinstance(obj, dict):
                msg = obj.get("msg")
                utc = parse_utc(obj.get("utc"))
                channel = obj.get("channel")
            else:
                continue

            if not (isinstance(msg, list) and len(msg) >= 3):
                continue
            event = msg[1]
            if not isinstance(event, str):
                continue
            records.append(Record(len(records), utc, channel, event, msg[2]))
    return records


def page_ids_in(record):
    """Return [(page_id, page_dict_or_None)] touched by this record."""
    out = []
    payload = record.payload

    if record.event in ("nodeAdded", "nodeRemoved"):
        if isinstance(payload, list) and len(payload) >= 2 \
                and payload[0] == "PageQueue":
            out.append((str(payload[1]), None))
        return out

    if record.event != "nodeChanged" or not isinstance(payload, list):
        return out

    for item in payload:
        if not isinstance(item, dict):
            continue
        queue = item.get("PageQueue")
        if not isinstance(queue, dict):
            continue
        for key, value in queue.items():
            if key == "ready":
                continue
            out.append((str(key), value if isinstance(value, dict) else None))
    return out


def build_pages(records, gap_seconds):
    pages = {}
    segments = []
    current = None
    last_page_id = None

    def start_segment(record):
        nonlocal current
        current = {
            "index": len(segments),
            "start_idx": record.idx,
            "end_idx": record.idx,
            "start_utc": record.utc,
            "end_utc": record.utc,
            "records": 0,
            "page_ids": [],
        }
        segments.append(current)

    for record in records:
        touched = page_ids_in(record)
        ids = [int(pid) for pid, _ in touched if pid.lstrip("-").isdigit()]

        # Status-only records do not define a segment; wait for the first
        # PageQueue record so a lone status event cannot create an empty one.
        boundary = current is None
        if current is not None and ids and record.utc and current["end_utc"]:
            if (record.utc - current["end_utc"]).total_seconds() > gap_seconds:
                boundary = True
        if current is not None and ids and last_page_id is not None \
                and min(ids) < last_page_id:
            boundary = True

        if boundary:
            start_segment(record)

        current["records"] += 1
        if ids:
            current["end_idx"] = record.idx
            current["end_utc"] = record.utc or current["end_utc"]

        for pid_str, data in touched:
            try:
                pid_int = int(pid_str)
            except ValueError:
                continue

            key = (current["index"], pid_str)
            page = pages.get(key)
            if page is None:
                page = Page(current["index"], pid_str)
                pages[key] = page

            if pid_str not in current["page_ids"]:
                current["page_ids"].append(pid_str)

            if page.first is None:
                page.first = record.utc or record.idx
            page.last = record.utc or record.idx

            if record.event == "nodeAdded" and page.added is None:
                page.added = record.utc or record.idx
            elif record.event == "nodeRemoved" and page.removed is None:
                page.removed = record.utc or record.idx

            if data is None:
                continue

            if "foil" in data and page.foil is None:
                page.foil = data["foil"]

            for side_name in ("Front", "Back"):
                side_data = data.get(side_name)
                if not isinstance(side_data, dict):
                    continue
                side = page.sides[side_name]

                state = side_data.get("state")
                if state == "Scanning" and side.scanning is None:
                    side.scanning = record.utc or record.idx
                elif state == "Safe" and side.safe is None:
                    side.safe = record.utc or record.idx
                elif state == "Ejected" and side.ejected is None:
                    side.ejected = record.utc or record.idx

                descriptor = side_data.get("Image")
                if isinstance(descriptor, dict) and side.descriptor is None:
                    side.descriptor = descriptor
                    side.image = record.utc or record.idx

            last_page_id = pid_int

    return pages, segments


def seconds(after, before):
    if isinstance(after, datetime) and isinstance(before, datetime):
        return (after - before).total_seconds()
    return None


def fmt(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def describe(pages, segments):
    print("== capture shape ==")
    print(f"segments: {len(segments)}")
    print(f"pages: {len(pages)}")
    print(f"image descriptors: "
          f"{sum(1 for p in pages.values() for s in p.sides.values() if s.descriptor)}")

    print("\n== segments ==")
    print("seg  records  pages  start_utc                 end_utc                   "
          "page-id range")
    for seg in segments:
        ids = sorted(int(x) for x in seg["page_ids"] if x.lstrip("-").isdigit())
        rng = f"{min(ids)}..{max(ids)}" if ids else "-"
        print(f"{seg['index']:>3}  {seg['records']:>7}  {len(seg['page_ids']):>5}  "
              f"{fmt(seg['start_utc']):<25} {fmt(seg['end_utc']):<25} {rng}")

    handles = Counter()
    compositions = Counter()
    compressions = Counter()
    media_windows = Counter()
    output_canvases = Counter()
    handle_pages = defaultdict(set)

    for (seg_idx, pid), page in pages.items():
        for side_name, side in page.sides.items():
            desc = side.descriptor
            if not desc:
                continue
            handles[desc.get("handle")] += 1
            compositions[desc.get("composition")] += 1
            compressions[desc.get("compression")] += 1
            media_windows[json.dumps(desc.get("mediaWindow"), sort_keys=True)] += 1
            output_canvases[json.dumps(desc.get("outputCanvas"), sort_keys=True)] += 1
            handle_pages[desc.get("handle")].add((seg_idx, pid))

    print("\n== descriptor fields ==")
    print("handles:", dict(handles))
    print("compositions:", dict(compositions))
    print("compressions:", dict(compressions))
    print("mediaWindow variants:")
    for key, count in media_windows.items():
        print(f"  {count:>4}  {key}")
    print("outputCanvas variants:")
    for key, count in output_canvases.items():
        print(f"  {count:>4}  {key}")
    print("distinct pages per handle:")
    for handle in sorted(handle_pages, key=lambda x: (x is None, x)):
        print(f"  handle {handle}: {len(handle_pages[handle])}")

    print("\n== state-transition durations (seconds) ==")
    transitions = {
        "Scanning->Safe": ("scanning", "safe"),
        "Safe->Image": ("safe", "image"),
        "Image->Ejected": ("image", "ejected"),
        "Ejected->removed": ("ejected", "__removed__"),
        "Scanning->removed": ("scanning", "__removed__"),
    }
    for label, (start_attr, end_attr) in transitions.items():
        values = []
        for page in pages.values():
            for side in page.sides.values():
                start = getattr(side, start_attr)
                end = page.removed if end_attr == "__removed__" else getattr(side, end_attr)
                delta = seconds(end, start)
                if delta is not None and delta >= 0:
                    values.append(delta)
        if values:
            values.sort()
            print(f"{label:<20} n={len(values):<4} "
                  f"min={values[0]:.3f} median={statistics.median(values):.3f} "
                  f"max={values[-1]:.3f}")
        else:
            print(f"{label:<20} n=0")

    print("\n== anomalies / limits ==")
    anomalies = Counter()
    for (seg_idx, pid), page in pages.items():
        for side_name, side in page.sides.items():
            tag = f"{side_name}"
            if side.image and not side.safe:
                anomalies[f"{tag}: image without Safe"] += 1
            if side.ejected and not side.image:
                anomalies[f"{tag}: Ejected without Image"] += 1
            if side.descriptor and side.descriptor.get("handle") not in (0, 1):
                anomalies[f"{tag}: unexpected handle"] += 1

    reused_ids = defaultdict(list)
    for seg_idx, pid in pages:
        reused_ids[int(pid)].append(seg_idx)
    reused_across_segments = {
        pid: segs for pid, segs in reused_ids.items() if len(set(segs)) > 1}
    print(f"page ids reused across segments: {len(reused_across_segments)}")
    for pid in sorted(reused_across_segments)[:10]:
        print(f"  id {pid}: segments {sorted(set(reused_across_segments[pid]))}")
    print("anomalies:", dict(anomalies) or "none")
    print("\nNote: nodeRemoved marks queue removal only. It does not prove the")
    print("image buffer was freed or that an upload succeeded.")


def write_csv(path, pages):
    fields = [
        "segment", "page_id", "side", "added_utc", "scanning_utc", "safe_utc",
        "image_utc", "ejected_utc", "removed_utc", "handle", "composition",
        "compression", "media_w", "media_h", "media_xres", "media_yres",
        "out_w", "out_h", "out_xres", "out_yres",
    ]
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for (seg_idx, pid), page in sorted(
                pages.items(), key=lambda kv: (kv[0][0], int(kv[0][1]))):
            for side_name in ("Front", "Back"):
                side = page.sides[side_name]
                desc = side.descriptor or {}
                media = desc.get("mediaWindow") or {}
                out = desc.get("outputCanvas") or {}
                writer.writerow({
                    "segment": seg_idx,
                    "page_id": pid,
                    "side": side_name,
                    "added_utc": fmt(page.added),
                    "scanning_utc": fmt(side.scanning),
                    "safe_utc": fmt(side.safe),
                    "image_utc": fmt(side.image),
                    "ejected_utc": fmt(side.ejected),
                    "removed_utc": fmt(page.removed),
                    "handle": desc.get("handle", ""),
                    "composition": desc.get("composition", ""),
                    "compression": desc.get("compression", ""),
                    "media_w": media.get("w", ""),
                    "media_h": media.get("h", ""),
                    "media_xres": media.get("xRes", ""),
                    "media_yres": media.get("yRes", ""),
                    "out_w": out.get("w", ""),
                    "out_h": out.get("h", ""),
                    "out_xres": out.get("xRes", ""),
                    "out_yres": out.get("yRes", ""),
                })


def write_json(path, pages):
    out = []
    for (seg_idx, pid), page in sorted(
            pages.items(), key=lambda kv: (kv[0][0], int(kv[0][1]))):
        item = {
            "segment": seg_idx,
            "page_id": pid,
            "added_utc": fmt(page.added),
            "removed_utc": fmt(page.removed),
            "foil": page.foil,
            "sides": {},
        }
        for side_name in ("Front", "Back"):
            side = page.sides[side_name]
            item["sides"][side_name] = {
                "scanning_utc": fmt(side.scanning),
                "safe_utc": fmt(side.safe),
                "image_utc": fmt(side.image),
                "ejected_utc": fmt(side.ejected),
                "descriptor": side.descriptor,
            }
        out.append(item)
    with open(path, "w") as fh:
        json.dump(out, fh, indent=2)


def main():
    ap = argparse.ArgumentParser(
        description="Offline Sifter event-bus lifecycle analysis")
    ap.add_argument("files", nargs="+", help="JSONL capture files")
    ap.add_argument("--session-gap", type=float, default=60.0,
                    help="seconds of silence that starts a new segment "
                         "(default 60)")
    ap.add_argument("--csv", help="write one row per page/side")
    ap.add_argument("--json", help="write structured lifecycle JSON")
    args = ap.parse_args()

    all_pages = {}
    offset_seg = 0

    for path in args.files:
        records = load(path)
        pages, segments = build_pages(records, args.session_gap)
        print(f"\n### {path}")
        describe(pages, segments)

        # Keep files separate in CSV/JSON by prefixing the segment index.
        base_offset = offset_seg
        offset_seg += len(segments)
        for (seg_idx, pid), page in pages.items():
            all_pages[(seg_idx + base_offset, pid)] = page

    if args.csv:
        write_csv(args.csv, all_pages)
        print(f"\nwrote {args.csv}")
    if args.json:
        write_json(args.json, all_pages)
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
