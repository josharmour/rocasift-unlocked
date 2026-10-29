#!/usr/bin/env python3
"""Poll the Sifter's authenticated EWS settings endpoint and append a
job-relevant timeline to JSONL. Usage: ews-poll.py <interval_seconds> <outfile>
Fields chosen as stall-relevant observables (card counters freezing,
hub connectivity flapping, CPU/process drift). Safe fields only."""
import base64, json, ssl, sys, time, urllib.request

HOST = "http://<LAN_IP>"          # http -> 301 -> https; go straight to https
URL = "https://<LAN_IP>/webservices/settings/all"
USER = "optra"
PWFILE = "<HOME>/.hermes/cache/scratch/sifter_ews_pw"

FIELDS = [
    "AdfFrontSideCount", "AdfBackSideCount", "ConnectedToHub", "NetworkOnline",
    "CPULoad1Minute", "CurrentProcesses", "FreeRAM", "SkillsRunning",
    "UptimeInSeconds", "FirmwareStatus", "DeviceTime",
]

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def fetch():
    pw = open(PWFILE).read().strip()
    tok = base64.b64encode(f"{USER}:{pw}".encode()).decode()
    req = urllib.request.Request(URL, headers={"Authorization": f"Basic {tok}"})
    with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
        return json.load(r)

def main():
    interval = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    outfile = sys.argv[2] if len(sys.argv) > 2 else "/tmp/ews-poll.jsonl"
    with open(outfile, "a", buffering=1) as out:
        while True:
            ts = time.strftime("%H:%M:%S")
            try:
                d = fetch()
                rec = {"wall": ts}
                for k in FIELDS:
                    rec[k] = d.get(k)
                out.write(json.dumps(rec) + "\n")
            except Exception as e:
                out.write(json.dumps({"wall": ts, "error": repr(e)}) + "\n")
            time.sleep(interval)

if __name__ == "__main__":
    main()
