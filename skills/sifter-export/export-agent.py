#!/usr/bin/env python3
"""Optra Edge skill: export chosen directories to an owner endpoint.

Env vars (from skill inputs via Azure IoT module twin):
  TARGET_PATHS      space-separated absolute paths to archive
  ENDPOINT_URL      HTTPS URL accepting POST multipart (field "payload")
  INTERVAL_SECONDS  loop interval; 0 or unset = single run then exit
  AUTH_TOKEN        optional bearer token

Emits machine-readable status lines on stdout:
  EXPORT_STATUS ok|error:<detail> bytes=<n> files=<n>
"""
import os
import sys
import tarfile
import tempfile
import time
import urllib.request
import uuid


def emit(status, bytes_=0, files=0):
    print(f"EXPORT_STATUS {status} bytes={bytes_} files={files}", flush=True)


def export_once():
    targets = os.environ.get("TARGET_PATHS", "").split()
    endpoint = os.environ.get("ENDPOINT_URL", "")
    token = os.environ.get("AUTH_TOKEN", "")
    if not targets or not endpoint:
        emit("error:missing_config")
        return

    total_files = 0
    with tempfile.NamedTemporaryFile(suffix=".tgz", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        with tarfile.open(tmp_path, "w:gz") as tf:
            for t in targets:
                if os.path.exists(t):
                    tf.add(t, recursive=True)
        size = os.path.getsize(tmp_path)
        # count entries for the status output
        with tarfile.open(tmp_path, "r:gz") as tf:
            total_files = sum(1 for _ in tf)

        boundary = uuid.uuid4().hex
        with open(tmp_path, "rb") as f:
            payload = f.read()
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="payload"; '
            f'filename="export-{int(time.time())}.tgz"\r\n'
            f"Content-Type: application/gzip\r\n\r\n"
        ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()

        req = urllib.request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                **({"Authorization": f"Bearer {token}"} if token else {}),
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            code = resp.status
        emit(f"ok:http_{code}" if code < 400 else f"error:http_{code}",
             size, total_files)
    except Exception as e:  # noqa: BLE001 — skill must never crash the loop
        emit(f"error:{type(e).__name__}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def main():
    interval = int(os.environ.get("INTERVAL_SECONDS", "0") or 0)
    while True:
        export_once()
        if interval <= 0:
            break
        time.sleep(interval)


if __name__ == "__main__":
    main()
