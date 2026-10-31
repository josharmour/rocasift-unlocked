#!/usr/bin/env python3
"""Correlate event-bus page ejections with portal batch counters.

Offline and read-only: this script reads saved JSONL captures only. It does
not contact the device or the portal.

Inputs
------
Bus capture(s): JSONL lines in either shape
    [2, "nodeChanged", [{"PageQueue": {"19": {"Front": {"state": "Ejected"}}}}]]
    {"utc": "...", "msg": [2, "nodeChanged", [...]]}
Portal snapshots: JSONL lines with at least
    {"utc": "...", "batch": 308663, "matched": 70, "unidentified": 0}

What it reports
---------------
For each bus segment and portal batch it prints the portal counter deltas next
to the number of bus pages that reached Ejected in the same interval. The
ratio is descriptive only: portal counters are cumulative for a batch, a bus
capture can start mid-batch, page ids are reused across segments, and neither
stream carries a per-item id that can be joined exactly.

Usage
-----
    python3 tools/correlate-portal.py BUS.jsonl [BUS2.jsonl ...] \
        --portal PORTAL.jsonl [--session-gap SECONDS]

Example
-------
    python3 tools/correlate-portal.py \
        device/research/live-sifter-20261031/sifter-live-20261031T0551.jsonl \
        device/research/live-sifter-20261031/events-continuation.jsonl \
        --portal device/research/live-sifter-20261031/sifter-portal-20261031.jsonl
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime


def parse_utc(value):
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def load_bus(paths):
    records = []
    for path in paths:
        try:
            handle = open(path, encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"{path}: cannot read ({exc})", file=sys.stderr)
            continue
        with handle:
            for lineno, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    print(f"{path}:{lineno}: skip invalid JSON ({exc})", file=sys.stderr)
                    continue
                utc = None
                msg = None
                if isinstance(obj, dict):
                    utc = parse_utc(obj.get("utc"))
                    msg = obj.get("msg")
                elif isinstance(obj, list):
                    msg = obj
                if msg is None:
                    continue
                records.append((utc, msg))
    return records


def page_ids(msg):
    """Return PageQueue ids touched by one decoded bus message."""
    ids = set()
    if not (isinstance(msg, list) and len(msg) >= 3):
        return ids
    payload = msg[2]
    if not isinstance(payload, list):
        return ids
    for item in payload:
        if isinstance(item, dict):
            queue = item.get("PageQueue")
            if isinstance(queue, dict):
                for key in queue:
                    if str(key).isdigit():
                        ids.add(int(key))
        elif isinstance(item, str) and item == "PageQueue":
            # nodeAdded/nodeRemoved carry a path list: ["PageQueue", "19", ...]
            pass
    if payload and payload[0] == "PageQueue" and len(payload) > 1:
        if str(payload[1]).isdigit():
            ids.add(int(payload[1]))
    return ids


def side_states(msg):
    """Yield (page_id, side, state) for nodeChanged PageQueue maps."""
    if not (isinstance(msg, list) and len(msg) >= 3):
        return
    payload = msg[2]
    if not isinstance(payload, list):
        return
    for item in payload:
        if not isinstance(item, dict):
            continue
        queue = item.get("PageQueue")
        if not isinstance(queue, dict):
            continue
        for key, value in queue.items():
            if not str(key).isdigit() or not isinstance(value, dict):
                continue
            for side in ("Front", "Back"):
                side_value = value.get(side)
                if isinstance(side_value, dict) and "state" in side_value:
                    yield int(key), side, side_value["state"]


def build_segments(records, gap_seconds):
    timed = [(utc, msg) for utc, msg in records if utc is not None]
    timed.sort(key=lambda pair: pair[0])
    segments = []
    current = None
    max_id = None
    for utc, msg in timed:
        ids = page_ids(msg)
        reset = bool(ids and max_id is not None and min(ids) < max_id - 20)
        gap = bool(current is not None and (utc - current["end"]).total_seconds() > gap_seconds)
        if current is None or gap or reset:
            current = {
                "start": utc,
                "end": utc,
                "records": 0,
                "ids": set(),
                "ejected_at": {},
                "max_id": max_id,
            }
            segments.append(current)
            max_id = None
        current["end"] = utc
        current["records"] += 1
        current["ids"].update(ids)
        for page_id, _side, state in side_states(msg):
            if state == "Ejected" and page_id not in current["ejected_at"]:
                current["ejected_at"][page_id] = utc
        if ids:
            local_max = max(ids)
            max_id = local_max if max_id is None else max(max_id, local_max)
            current["max_id"] = max_id
    return segments


def load_portal(path):
    batches = defaultdict(list)
    try:
        handle = open(path, encoding="utf-8", errors="replace")
    except OSError as exc:
        sys.exit(f"{path}: cannot read ({exc})")
    with handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"{path}:{lineno}: skip invalid JSON ({exc})", file=sys.stderr)
                continue
            utc = parse_utc(obj.get("utc"))
            batch = obj.get("batch")
            matched = obj.get("matched")
            unidentified = obj.get("unidentified", 0)
            if utc is None or batch is None or matched is None:
                print(f"{path}:{lineno}: skip record without utc/batch/matched", file=sys.stderr)
                continue
            batches[batch].append(
                {
                    "utc": utc,
                    "state": obj.get("state", ""),
                    "matched": int(matched),
                    "unidentified": int(unidentified),
                }
            )
    for rows in batches.values():
        rows.sort(key=lambda row: row["utc"])
    return batches


def fmt_time(value):
    return value.strftime("%H:%M:%S")


def report_segment(segment_index, segment, batch_id, snapshots):
    print(f"\nsegment {segment_index}  {fmt_time(segment['start'])}..{fmt_time(segment['end'])}"
          f"  records={segment['records']}  pages={len(segment['ids'])}"
          f"  ejected={len(segment['ejected_at'])}")
    print(f"batch {batch_id}")

    before = [row for row in snapshots if row["utc"] <= segment["start"]]
    during = [row for row in snapshots if segment["start"] < row["utc"] <= segment["end"]]
    after = [row for row in snapshots if row["utc"] > segment["end"]]

    baseline = before[-1] if before else (during[0] if during else None)
    rows = []
    if baseline is not None:
        rows.append(baseline)
        rows.extend(row for row in during if row is not baseline)
        rows.extend(after[:1])
    else:
        rows.extend(during)

    if len(rows) < 2:
        print("  no usable portal snapshots around this segment")
        return

    header = ("  utc       state                        matched  d_matched"
              "  unidentified  d_unid  pages_ejected  matched/page")
    print(header)
    previous = rows[0]
    print(f"  {fmt_time(previous['utc'])}   {previous['state'][:28]:28}"
          f" {previous['matched']:8d}          -"
          f" {previous['unidentified']:13d}       -"
          f" {0:14d}             -")
    window_pages = 0
    total_matched_delta = 0
    for row in rows[1:]:
        pages = sum(
            1 for when in segment["ejected_at"].values()
            if previous["utc"] < when <= row["utc"]
        )
        d_matched = row["matched"] - previous["matched"]
        d_unid = row["unidentified"] - previous["unidentified"]
        ratio = f"{d_matched / pages:.2f}" if pages else "-"
        marker = " *after end*" if row["utc"] > segment["end"] else ""
        print(f"  {fmt_time(row['utc'])}   {row['state'][:28]:28}"
              f" {row['matched']:8d} {d_matched:10d}"
              f" {row['unidentified']:13d} {d_unid:7d}"
              f" {pages:14d} {ratio:>12}{marker}")
        window_pages += pages
        total_matched_delta += d_matched
        previous = row

    ratio = f"{total_matched_delta / window_pages:.2f}" if window_pages else "-"
    print(f"  summary: matched {total_matched_delta:+d} across {len(rows)} snapshots,"
          f" pages ejected in segment {len(segment['ejected_at'])},"
          f" within snapshot window {window_pages},"
          f" matched/page(window) {ratio}")
    print("  note: cumulative batch counters; capture may start mid-batch;"
          " page ids are reused across segments.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bus", nargs="+", help="bus capture JSONL file(s)")
    parser.add_argument("--portal", required=True, help="portal snapshot JSONL file")
    parser.add_argument("--session-gap", type=float, default=60.0,
                        help="split a bus capture on a timestamp gap larger than this (default 60)")
    args = parser.parse_args()

    records = load_bus(args.bus)
    segments = build_segments(records, args.session_gap)
    batches = load_portal(args.portal)

    print(f"bus records with timestamps: {sum(1 for utc, _ in records if utc is not None)}")
    print(f"segments: {len(segments)}")
    print(f"portal batches: {', '.join(str(b) for b in sorted(batches))}")
    print("\nNote: this joins aggregate counters to aggregate page counts."
          "\nIt cannot prove that a specific page was uploaded or indexed.")

    for batch_id in sorted(batches):
        snapshots = batches[batch_id]
        print(f"\n== batch {batch_id} ({len(snapshots)} snapshots) ==")
        for index, segment in enumerate(segments):
            report_segment(index, segment, batch_id, snapshots)


if __name__ == "__main__":
    main()
