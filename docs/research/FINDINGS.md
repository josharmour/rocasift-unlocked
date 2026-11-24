# Roca Sifter — Recon Findings
Collected 2026-10-24 by Hermes (session: roca firmware/RE investigation).
Observations are marked [O]; inferences are marked [I].

## 1. What the device is

| Field | Value | Source |
|---|---|---|
| Product | Roca Sifter (TCGplayer card sifter) | [O] |
| Maker | Roca Robotics Inc. (TCGplayer/Lexmark subsidiary) | [O] T&C pdf |
| Platform | Lexmark **Optra Compute 550** white-label (Machine type `8085-001`, unit P/N `10U0900-003`, mainboard `10U9020 REV 4`) | [O] device serves /device-models/compute550.png; cert O=Lexmark; chassis & PCB labels |
| CPU / RAM / storage | Marvell 88PA6270 ("Pegmatite") Quad-core ARMv8-A / 4 GB DDR4 (`4× Nanya NT5AD1024M8C3-HR`) / 16 GB Kioxia eMMC 5.1 (`THGAMVG7T13BAIL`) | [O] board photos + UART boot log |
| OS | Poky Linux (Yocto), secure boot, Azure IoT Edge runtime, Docker "skills" | [O] spec sheet |
| Serial | 808563180009W | [O] cloud + device |
| Azure identity | thingName sifter-808563180009W, DPS scope 0ne00197463 | [O] |
| Build target | granite2v8-sifter (OEM_ID 2, Family Roca, Series TCGPlayer) | [O] device settings API |
| **Firmware** | **3.5.4** | [O] device settings API |

## 2. Network presence (Josh's LAN)

- Wired: **<LAN_IP>** (MAC <MAC>, Lexmark OUI; mDNS `optra-808563180009W`)
- Wireless: **<LAN_IP>** (MAC <MAC>)
- Both serve the same EWS on :443 — "TCGplayer Device Setup" (Vite SPA),
  self-signed cert CN=optra-808563180009W. Server banner: `webserver`.
- Setup-mode AP portal mirrors EWS at http://172.16.131.2/setup (advanced
  network config at http://172.16.131.2). [O] Roca setup docs
- Rate limiter: ~8 rapid requests -> 429. Space probes 3-5s. [O]

## 2b. Network-path observation (2026-10-27) [O]

Owner switched the Sifter from Ethernet (<LAN_IP>) to Wi-Fi (<LAN_IP>)
and immediately observed the longest successful scan run in a while
(more cards processed than recent attempts). Single data point — could be
routing/latency differences between paths, radio conditions, or chance.
Action: compare job success/throughput over several runs on each path
before drawing conclusions.

## 3. Local EWS API (authenticated)

Auth: `Authorization: Basic base64("optra:" + devicePassword)`.
`POST /login {password}` only validates (200 {} = correct). No cookie/session.

Endpoints (enumerated from SPA bundle index-COcuR-dg.js):
```
POST /login {password}
GET  /webservices/settings/<key[,key...]>     PUT /webservices/settings/
GET  /webservices/logs                        (~10MB PKCS#7 envelopedData,
                                               sealed to Lexmark support cert
                                               padebug.lpdev.prtdev.lexmark.com
                                               - NOT readable locally)
GET  /webservices/diagnostics/screenshot      (500: no display attached)
GET  /webservices/diagnostics/external/urls
GET/PUT/DELETE /webservices/proxy             POST /webservices/proxy/test
POST /webservices/password {password}
GET  /webservices/wireless/{interface,networks,psk}
```
Settings keys observed in bundle: BuildTarget, FamilyName, FirmwareVersion,
ModelName, OEM_ID, ScopeId, SerialNumber, SeriesName, LastTimeSync, HDMI_Jack,
Wired_/Wireless_IPv4_*, ethaddr, wlanaddr, Manual_DNS/NTP_*, ConnectedToHub.
Unknown /webservices/* paths fall through to the SPA (no hidden endpoints). [O]
Endpoint surface does NOT change during a running job (verified mid-job). [O]

## 3b. Settings dump + hidden services (2026-10-28) [O]

Authenticated `GET /webservices/settings/all` returned 121 keys
(archived local: `device/settings-all-20261028.json`). Highlights:
Hailo AI accelerator telemetry keys (`HailoChipTempC`), 4 GB RAM,
NVMe footprint unpopulated, eMMC health telemetry, TPM EK, `Pull_FW_URL`
(custom firmware pull URL), `SettingsPort8080` hidden toggle, fan control
keys, WindowManager/WebBrowser flags, controller-card barcode
10U900005000161921976 (distinct from 10U9020 mainboard).

Rate limiter: after a ~120-request burst, device-global 429 ban persisted
>20 min (both interfaces affected — ban is per-device, not per-IP).
Documented folklore "~8 requests" understates the penalty window.

**SettingsPort8080 experiment**: PUT true → verified; port 8080 stayed
closed (likely needs reboot). BUT follow-up scan found **port 5000 open:
"Sifter Vision API"** (FastAPI/uvicorn, x-api-version 1.8.10) —
`sifter/recognize_card` accepts a card image multipart and returns full
TCGplayer catalog identification ON-DEVICE in ~0.6s, no auth.
Verified: Cruel Finality / Aether Revolt #54 / tcgp 126467 from our own
export scan. Public writeup: `docs/vision-api.md`. This is the local
control breakthrough — core function callable on-LAN without cloud.
Whether SettingsPort8080 gates port 5000 unconfirmed (reboot test pending).

## 3c. Live job instrumentation + local control (2026-10-27 evening) [O]

Monitored a failing Scan & Sift job (settings poll 10s + Vision /ram 5s,
timeline in session log). Results:

- Working phase: RAM 22%→27.6% climbing, CPU 0.5→1.3, processes 434→449.
- Stall (~3 min in): RAM PLATEAUS, CPU decays, processes stable, network
  up, SkillsRunning=2. **Nothing crashes — device healthy but idle.**
  Portal stuck "in progress", zero results uploaded.
- Conclusion [I]: orchestration stops commanding the device; not a local
  crash/OOM/hardware fault. Matches the ~2-min death seen in the §8 mitm
  experiment — suspect a cloud callback/timeout wedge.

Local control proven via port 5000 (Vision API):
- `POST /sifter/reset` → "Sift has been reset."
- `POST /sifter/initialize {"game":"MTG"}` → "Sift initialized successfully
  for game: MTG with foiling type: Foil" — spawned new worker processes
  (448→452), RAM resumed climbing. Pipeline responds to direct local
  commands with no cloud involvement.

Full TCP port scan (all 65535): open = 80, 443, 5000, 5355(LLMNR),
**9002, 21586, 21587**. The latter three accept TCP but speak binary
protocols (no HTTP/TLS response) — internal service channels, candidates
for the camera-frame bus / motor-controller link / IoT Edge internals.
Motor control is NOT exposed via the Vision API; actuation path still
unidentified pending root/UART or protocol RE on these ports.

## 3d. Cloud-side job state + vendor incident correlation (2026-10-28) [O]

Read TCGplayer's own API from the seller portal session (ql-api.tcgplayer.com;
evidence archived: `device/portal-api/ql-api-evidence-20261028.json`):

- Job `a5f7bfb9` (23:15 stall): server reports **cardsProcessed=21**, but
  batch 299842 matched-items remained **0** indefinitely (past their
  "wait 5 min" advice). Results lost between recognition counting and
  batch persistence.
- Job `f5502dc7` (23:51): cardsProcessed stayed **0** while cards were
  physically fed through the machine.
- Device record: status InProgress, connected=true, IoT connection flapped
  ~23:02–23:06 PDT; lastJobUpdatedAt froze at 23:58.
- Portal auto-paused the job without owner input; Resume did NOT revive
  the machine (device vitals unchanged).
- Portal console showed SignalR notification-hub connection failures
  (quicklist-notifications.tcgplayer.com) before recovering.

Vendor incident (status page + email, opened 2026-10-16, still
"Investigating" as of 10-27): "Roca Sifter/Scan & Identify Processing
Times and Errors" — peak-hour overload, all users; advice: don't delete
failed jobs/batches, wait 5 min and refresh. Our measurements are a
sharper version of their own symptom description and localize it to the
recognition→batch persistence chain.

Project implication [I]: the local Vision API (port 5000) bypasses this
broken cloud results-pipeline entirely — recognition works on-device even
while the vendor's results chain is down.

## 3e. Vision API re-verified live + score semantics (2026-10-30) [O]

Re-probed the device at `<LAN_IP>` (`optra-808563180009w`) during a live
Scan & Sift job. Service unchanged: uvicorn, `x-api-version: 1.8.10`,
self-documenting at `/openapi.json`. Ports open: 80, 443, 5000; **8080
still closed** — `SettingsPort8080` remains unproven as a gate for 5000.

Recognition is faster than the 2026-10-27 capture on the same image:
`rec_time` 0.256 s / `full_time` 0.289 s (was 0.438 / 0.592). Output is
deterministic — same `card_id`, same `tcgp_catalog_code` 126467, same
`recognition_score` 0.555 for `images/50952597.jpg`.

**The API never reports "unknown".** Every response carries
`"detail": "Card recognized successfully."`, including for input that is
not a card at all. `recognition_score` is the only quality signal, and it
can be negative:

| Input | Returned | Score |
| --- | --- | --- |
| Cruel Finality (`50952597`) | Cruel Finality / Aether Revolt | 0.555 |
| Druid of the Cowl (`50952633`) | Druid of the Cowl / Aether Revolt | 0.722 |
| Ice Over (`50953011`) | Ice Over / Aether Revolt | 0.540 |
| Implement of Combustion (`50953510`) | Implement of Combustion / Aether Revolt | 0.490 |
| card back (`50955028`) | *Back of a Magic Card* / **Sorting Robotics Extra** | **−0.027** |
| blank gray JPEG (446×600) | *Find the Assassin (cont'd)* / **Assassin's Creed Minigames** | 0.185 |

Two synthetic catalog sets act as catch-all classes for non-card imagery:
`Sorting Robotics Extra` and `Assassin's Creed Minigames`. Their
`tcgp_catalog_code` values are not numeric — e.g.
`Sorting Robotics Extra-Back of a Magic Card.jpg`.

[I] The batch-289675 unidentified card (`50955028`, sequenceId 40) is a
scan of a card **back**, not a recognition failure: mean RGB [118,102,86]
(brownish) against [135,140,126] for a normal card in the same batch. The
cloud left it unidentified because it thresholds; the local API does not.

[I] Any consumer treating `detail` as success will inject synthetic entries
into exports. Threshold on `recognition_score` instead; in this six-sample
set ~0.3 separates real matches (0.49–0.72) from non-card input (−0.03–0.19).
Not yet calibrated against a larger sample.

Undocumented initialize fields: `InitializeRequest` accepts `game`,
`foiling_type`, `block_list`, `inclusive_set_list`. The latter two are
set-filtering controls not described in `docs/vision-api.md`.

Reproduce:

    curl -s http://<device-ip>:5000/openapi.json
    curl -s http://<device-ip>:5000/ram
    curl -s -X POST http://<device-ip>:5000/sifter/recognize_card \
      -F "file=@images/50952597.jpg;type=image/jpeg" \
      -F "is_foil=false" -F "is_pre_cropped=false" -F "half_card=0"

RAM sampled every ~5 s for four minutes during that same job (`/ram`,
unauthenticated). Sawtooth, not a plateau:

    06:10:30–06:11:56   27.6–28.1 %   steady
    06:12:01            24.8 %        single-sample dip
    06:12:06–06:12:22   25.2→28.2 %   re-climb over ~20 s
    06:12:27–06:14:28   27.5–28.0 %   steady

[I] The dip-and-reclimb reads as per-batch worker teardown and reallocation:
the job was still cycling batches at **11+ minutes in**, well past the ~3 min
point where the §3d stall was observed on other runs.

[I] Methodological consequence for §3c/§3d instrumentation — **a flat `/ram`
reading alone is not evidence of a stall.** Steady-state scanning produces an
equally flat trace between batch boundaries. Distinguishing stalled from busy
requires either CPU decay (EWS `CPULoad*`, authenticated) or the absence of a
batch-boundary dip over an interval longer than one batch cycle.

## 4. Cloud side (ql-api.tcgplayer.com, seller session cookies)

Auth via lifted browser cookies (chrome-faithful); CORS blocks page-JS fetches
of images but local curl with cookies works fine.

```
GET  /batch/<id>                              counts + config
POST /search/batch/<id>/matched-items   {page,pageSize}
POST /search/batch/<id>/unidentified-items    same shape
GET  /sifters/seller                          all devices + state
GET  /sifters/<deviceId>                      single device detail
GET  /jobs/<jobId>                            job config + progress
GET  /images/<batchId>/<batchItemId>/thumb.jpg   446x600 JPEG, ONLY rendition
                                                  (no full-size variant exists;
                                                  probed full/original/large/etc)
```
No directory listing anywhere; batchItemIds are non-sequential.
NO remote device-log/diagnostics endpoints on ql-api (404s). [O]

## 5. Data harvested -> this folder

- `batch-289675-scans.json` — full scan list snapshot (501 items) + batch meta
- `manifest.csv` — 501 rows: name/set/number/condition/printing/language/
  confidence/pricing/marketPrice/bin/imageUrl per scan
- `images/` — 501 scan JPEGs (48MB), all verified valid 446x600
- Batch 289675 ("MTG-20261024134859"): $71.45 total pricing, all confidence=Good,
  Aether Revolt, 0 duplicates
- Second job batch **290069** observed live (foil sift); not harvested yet

## 6. Vendor infrastructure map

| Endpoint | Purpose | Access |
|---|---|---|
| portal.optra.com | Lexmark Optra Portal (device mgmt) | auth required; GraphQL API host injected post-login; CF blocks anon POST |
| optra-release.azure-devices.net | Azure IoT Hub | device-only |
| global.azure-devices-provisioning.net | Azure DPS | device-only |
| optrarelease.azurecr.io | Azure Container Registry (skill images) | anon pull DISABLED (401 even per-repo) |
| bucket.optra.com | S3: **firmware downloads on update** [O user guide] | listing 403; object ACLs unknown |
| logsene-journald-receiver.sematext.com | app log upload / remote diagnostics | device-only |
| mcr.microsoft.com + *.blob.core.windows.net | IoT Edge base images + ACR image deltas | public |

## 7. Firmware availability

- No public firmware downloads exist for Optra Edge devices or the Sifter.
  Firmware is portal-managed OTA; delivered from bucket.optra.com on update,
  skill containers from optrarelease.azurecr.io. [O docs + user guide]
- "granite2v8" build target: zero public hits.
- LexmarkVentures GitHub has only skill SDK examples, no device firmware.
- Community RE of the Sifter: none found (hardware shipped Sept 2026).

## 8. MITM capture experiment (2026-10-24) — tested, NOT viable for jobs

- Device honors `PUT /webservices/proxy` (port must be a STRING). Intercept
  mode rejected (`tlsv1 unknown ca` — Lexmark/Azure-root-only trust store);
  pass-through mode (`--ignore-hosts '.*'`) tunnels fine.
- Applying the proxy bounces the device (~1min EWS + cloud outage, self-recovers).
- Even sequenced correctly (proxy → stable → job start), the job died ~2min in
  (white flashing light, 0 cards). Tunnel can't sustain job traffic.
- Yield: new hosts `secretsmanager.us-east-1.amazonaws.com` (device pulls
  runtime secrets — likely ACR creds/job tokens) and `apis.us.iss.lexmark.com`.
- Logs in `mitm/`.

## 9. USB device port enumeration (2026-10-27) [O]

Plugged the rear USB-B (device) port into the Mac (macOS 27.0.1), data-capable cable:

- Enumerates as **"Lexmark xxxx"**, VID `0x043D` (Lexmark), PID `0x0122`,
  serial `1235`, USB 2.0 High-Speed (480 Mbps), bcdUSB 2.00, device class 0
  (per-interface). Attach visible in `log show` (icdd) and ioreg.
- Interfaces: `(3,0,0)` HID, `(ff,ff,ff)` vendor-specific,
  `(7,1,2)` USB printer class (bidirectional).
- **No network gadget**: no new `en*` interface, no 169.254.x.x self-assigned
  address, no `_http._tcp` Bonjour appearance. The Optra Compute doc's
  "EWS over USB at 169.254.76.86" behavior is NOT present on firmware 3.5.4 —
  the device-role port presents as a printer-class composite device instead.
- [I] The vendor-specific interface is the interesting one for RE (possible
  job/control channel); printer class suggests standard print-path exposure.
- Raw capture: `device/usb-ioreg-dump-20261027.txt` (full `ioreg -p IOUSB -w0 -l`
  while connected).
- Note: the dump also shows a "CONNECT 6" (Lewitt GmbH) device on the same hub —
  that is an unrelated audio interface on Josh's desk hub, NOT part of the
  Sifter. Ignore it when reading the dump.

## 9b. Linux-side USB probe (2026-10-27) [O]

Host: omarchy 7.2.8-9 (x86_64), kernel drivers as noted. Sifter rear USB-B →
VIA Labs desk hub → Pixelbook. Setup: `pacman -S usbutils python-pyusb`
(libusb already present). Probe tool: `tools/usb-probe.py`; bus sniffer:
`tools/usbmon-sniff.py` (new, see below).

- Enumeration matches macOS exactly: `043d:0122` "Lexmark xxxx", serial `1235`,
  High-Speed 480M. Kernel bindings: `usblp` → iface 1 (bidirectional, proto 2),
  `usbhid`/`hid-generic` → iface 2 (hidraw2/hiddev96); **iface 0 unclaimed**.
- Full descriptor dump (`device/usb/usb-desc-20261027.txt`,
  `usb-lsusb-v-20261027.txt`):
  - iface 0 class ff/ff/ff, **iInterface string = "Scan"** — bulk OUT `0x02` +
    bulk IN `0x82`, 512-byte packets
  - iface 1 printer 07/01/02 bidirectional, iInterface "Print" — bulk
    OUT `0x01` + IN `0x81`, 512-byte
  - iface 2 HID, interrupt IN `0x83`, 64-byte, 16 ms interval
  - bcdDevice 0.00, self-powered, bMaxPower 2 mA; device qualifier advertises
    device class 7 (printer)
- The vendor interface being *named* "Scan" is the strongest hint yet that it
  carries the scan-data channel. [O]
- HID report descriptor (73 B, fetched via sysfs
  `usb-hid-report-descriptor-20261027.txt`): Application collection, Report
  ID 1, then seven consecutive 8-bit Data,Var,Rel inputs (usages numbered
  3..9 under an unusual usage page value) → reports are `[id][7 bytes]` on
  EP3. Likely a button/status vector; semantics unknown until pressed.
- **Idle silence** [O]: listen on Scan iface EP IN for 120 s and again for
  600 s → zero transfers; hidraw nonblocking read 5 s → nothing; printer IN
  nonblocking → nothing pending; usbmon pure-idle → zero bytes in 4 s. Across
  ~13 min of idle listening the device transmitted nothing unprompted.
- Printer-class write test [O]: `ESC E` (PCL reset) written to
  `/dev/usb/lp0` was accepted without error; no reply within 8 s. CUPS is
  installed but has no queue configured; raw device write is the working path.
- usbmon quirks on this kernel [O]: event header is **48 bytes** (classic docs
  say 64 — extra tail fields absent), poll()/select() wakeup effectively fires
  once per open (sleep-poll draining required), and an interrupt urb submitted
  without timeout pends silently (one SUBMIT event, no callbacks). Encoded in
  `tools/usbmon-sniff.py`, which auto-detects the header size and was
  validated against self-generated control/bulk/interrupt traffic.
- [I] The Scan interface almost certainly needs host-initiated commands on
  EP `0x02` OUT before it will produce data on `0x82` IN — nothing appeared
  spontaneously. Stage 4 of the runbook (careful replay of captured frames)
  is the next lever once a stimulus capture exists.
- Captures live in `device/usb/` per the runbook naming convention.

## 9c. What official Lexmark documentation says about the ports (2026-10-27) [O]

Sources: `reference/optra-compute-ug.pdf` (Optra Compute User's Guide,
Feb 2021) and `reference/optra-ug.pdf` (multi-model User's Guide, Nov 2025 —
current); both agree verbatim for Compute 500/550. Online copies:
optra.com/User-Guide-en.pdf, optra.com/Optra Compute User's Guide.pdf.

| Port | Official function (verbatim intent) |
|---|---|
| USB port (Type-A, host role) | "Attach a supported USB device, such as a flash drive or the MarkNet network adapter (purchased separately)." Setup note: required for Wi-Fi via MarkNet when no Ethernet is available. |
| USB device port (USB-B) | "Connect the device to a computer to access the Embedded Web Server (EWS) and manage on-device settings." Intended for initial network configuration: plug into a computer, browse **169.254.76.86**, enter the device serial number as the password. "We recommend using a computer running Windows 10." |

That is the ENTIRE documented surface for both ports:

- No documented scan-data, print-job, or HID/button role for either port.
- No documented firmware-update role over USB ("Pulling firmware" LED state
  refers to network pulls from bucket.optra.com).
- The Windows-10 recommendation plus link-local addressing strongly suggests
  an RNDIS/CDC network gadget for EWS-over-USB — which fw 3.5.4 does NOT
  present (§9/§9b: no en* interface, no gadget). Either Roca's build dropped
  it or it needs conditions we haven't met.
- The composite HID + vendor-"Scan" + printer-class enumeration we found is
  UNDOCUMENTED — print-engine heritage surfacing through the Optra build,
  not part of the official Optra Compute story.
- Cross-model context from the Nov 2025 guide: newer models converge the
  roles — CX2000 and VZ5100/VZ6100 label their USB 3.0 ports as BOTH
  "connect to a computer to access the EWS" AND "attach a supported USB
  device". The dual-role future is one port doing both.
- All models carry an identical warning: "do not touch the USB cable or the
  device in the areas shown while actively operating" — generic chassis
  boilerplate, not evidence of active USB data flow during jobs.
- Related lead: docs.optra.com describes skills as Docker containers "given
  access to a set of underlying hardware on the devices" — if skill
  containers can reach the scanner/camera or USB subsystem, an owner-deployed
  skill is a potential SUPPORTED local-control route worth investigating
  separately from raw USB RE.

## 9d. Stimulus captures during a live job + buttons (2026-10-27 evening) [O]

Setup: dual capture across a portal-driven Scan & sift job — bus-wide usbmon
(dev5-filtered) + `listen-ff` claim-polling EP `0x82` — plus a passive reader
holding `/dev/usb/lp0` open so printer-IN polling existed. Files:
`device/usb/usb-usbmon-job-20261027.txt`, `usb-ff-job-20261027.txt`,
`usb-lp0-job-20261027.txt`.

- Owner reported the job scanned ~10 cards then paused (the recurring stall
  pattern). Across the whole window the USB side recorded **ZERO
  device-originated events**: no HID reports on EP `0x83`, no printer traffic
  on `0x01`/`0x81`, no Scan-interface data on `0x82` despite continuous
  polling, no device-initiated control requests.
- The only non-poll events in ~15 min were host-side artifacts of our own
  tooling: the lp0 reader's 1024-byte read-ahead submit on EP `0x81`, and a
  control-transfer burst (HID class descriptor 10 B + report descriptor 73 B)
  caused by reattaching usbhid mid-capture.
- Printer-IN behaves as a silent pend: one SUBMIT, no CALLBACK — consistent
  with "device has nothing to deliver unless something is written to printer
  OUT first".
- Button presses (~18:02) produced no HID events, but **this trial is INVALID
  as a HID test**: usbhid had been detached by an earlier probe and was only
  reattached at ~18:03, so EP `0x83` was unpooled during the presses. A redo
  with polling live is pending.
- Lesson encoded in the runbook: after `detach_kernel_driver`, ALWAYS
  `attach_kernel_driver` on release — the missing hidraw went unnoticed for
  ~15 min and invalidated a test.
- [I] On fw 3.5.4 the USB device port is inert during normal cloud-driven
  operation; the scan pipeline is internal (camera → SoC → cloud over
  Ethernet/Wi-Fi). The composite USB interfaces are dormant scaffolding from
  the Lexmark print stack.
- [I] Getting data over USB will require actively driving the vendor protocol
  on EP `0x02` OUT (runbook Stage 4), not passive listening.
- Postscript: all three capture processes were terminated when the host
  slept (~18:14) — usbmon ended at `Errno 112 Host is down`, listeners at
  `Errno 5 I/O Error`. Zero transfers were recorded up to termination,
  reinforcing the silence finding. After resume the VIA hub and device were
  absent from lsusb entirely; replug required for further work.

## 10. Routes to firmware bits (remaining)

1. **Physical** — UART pads / eMMC dump on the Compute 550 board; secure boot
   limits writing, reading usually works. Highest-yield remaining option.
2. **Ask** — Roca support (support@rocarobotics.com) or Lexmark Optra support
   (optra.techsupport@lexmark.com) for a firmware image.

Note: Roca T&C contains a software reverse-engineering restriction clause.

## 10b. Skill-container route (2026-10-27) — legitimate local access

Source: docs.optra.com/skills/overview (official Optra Edge docs).

[O] Optra Edge skills are **ARM64 Docker containers** built by anyone from
their own images (Docker Hub / Azure ACR / private registries; AWS ECR not
supported) or Docker Compose TARs. Deployment is via the Optra portal:
Library → add skill from image → attach to a workflow → deploy to a device.
Config arrives via Azure IoT module twin; outputs flow back as IoT messages.

[O] Skills can request **privileges**: cameras, audio, removable media,
file system volumes, GPIO pins, and more (docs.optra.com/skills/privileges).
A skill with file-system + removable-media privileges could plausibly read
the scan pipeline's outputs and write to USB — the owner-controlled export
goal, using the vendor's own mechanism.

Routes to obtain a running skill container on the Sifter:
1. **Owner portal claim** [I]: create an Optra portal org
   (optraportal.com), register the Sifter into it. Open question: the
   device is provisioned via Roca/TCGplayer DPS scope 0ne00197463 — whether
   an owner can re-claim it needs confirmation from Roca support or the
   TCGplayer account.
2. **Ask Roca** to deploy an owner-authored skill or grant portal access.
3. **UART/root route** remains the control-plane complement (skill =
   sandboxed data plane; console = full control).

Skill design (draft, ready to build):
- Minimal ARM64 Alpine image with a small agent: tar selected directories,
  POST to owner's server; or dropbear SSH for interactive access.
- Manifest: inputs = target paths/endpoint; privileges = file system
  volumes + removable media; outputs = status/byte counters.
- Registry: Docker Hub (device already pulls from Azure ACR, so outbound
  registry access likely works).

Caveats [I]: container is sandboxed (not a root shell); privilege approval
process for third-party skills unknown; portal claim feasibility unknown.

## 10c. Firmware format intelligence + extraction routes (2026-10-27)

[O] Official Optra docs (docs.optra.com/devices/firmware): firmware is
portal-managed OTA only — statuses Requesting → Downloading → Downloaded →
Applying → Rebooting → Ready; no manual image distribution and no .fls
downloads offered for Optra Edge devices.

[O] Lexmark's printer-lineage firmware format is **.fls**: a PJL NETFLASH
stanza (`@PJL COMMENT NETFLASH ID=... RIP="ver" ENG=... IOT="1.1.26+git0+hash"
FLASHOPTS=...`) followed by binary sections (kernel + rootfs with sizes in the
header, `KERNELENCR=3` = encrypted kernel sections, `FKSIGNSZ` = signature
block). Public teardown of a granite2-family .fls:
https://haxx.in/posts/wtm-wtf (2024) — also documents that current Lexmark
firmware added rootfs encryption and rollback prevention.

[O] Our device's build target is `granite2v8-sifter` — same granite2 platform
family as current Lexmark printers — and .fls headers carry Yocto-style IOT
version strings, consistent with the Poky/Yocto base OS.

[I] The Sifter's OTA artifact is most likely a granite2-family .fls-style
NETFLASH blob (or derivative) fetched from bucket.optra.com over HTTPS and
signature-checked against secure boot. Exact container unconfirmed until we
capture one.

Extraction routes, ordered by cost:

1. **Learn the OTA object URL, then anonymous-GET it** from bucket.optra.com
   (directory listing is 403; per-object ACLs unknown). Observe the portal's
   "Update Firmware" flow via browser devtools for version metadata/object
   keys; probe common S3 key patterns.
2. **Probe the device webserver for print-heritage firmware endpoints**
   beyond `/webservices/*` — the SPA only maps that namespace, but Lexmark
   print servers traditionally expose more (`/cgi-bin/`, update pages,
   `Update Firmware` handlers). Cheap to enumerate from the EWS.
3. **Physical (highest yield; BOARD-NOTES Phase 4)**: UART → U-Boot →
   `ums 0 mmc 0` full-eMMC dump over USB mass storage → dissect partitions
   locally with binwalk (bootloader / kernel / rootfs / data / docker
   layers). Rootfs likely squashfs or ext4; kernel sections may be encrypted
   per KERNELENCR.
4. **Ask** Roca/Lexmark support for a firmware image.

Caveat [O]: the device rejects unknown CAs for TLS interception (§8), so
capturing OTA download CONTENT requires an endpoint the device trusts or a
trusted proxy position — pass-through capture yields SNI/hostnames only.

## 10d. JPRG1 header — UART hunt closed (2026-10-28)

Session moved to hermes.local (USB-TTL adapter lives here). Outcome: JPRG1 is
very unlikely to be a debug UART; evidence points to a factory programming bus.

[O] Adapter chain proven good BEFORE blaming the board: CP210x loopback echo
test captured ~255 KB of echoed PING markers (`device/uart/boot-115200-r3.log`,
which caught the echoes after an orphaned reader stole them), and an RXD→GND
hold produced logged zeros. Isolation ladder: adapter RX alive → RX solid →
full TX/RX loop, all passing.

[O] Continuity and multimeter survey on `21_JPRG1` (counting from the
silkscreened pin-1 marker): position 2 = GND; positions 3 and 6 idle at
≈ 3.6 V, others low. Adapter captures with position 2 as ground (`115200` baud
on positions 3 and 6 during power-cycles) produced zero bytes
(`device/uart/boot-115200-pos3.log`, `boot-115200-pos6.log`). Wrong-baud
captures normally still yield misframed bytes; zero bytes across pins means no
async UART edges were present.

[I] Two pins idling high at ~3.6 V is consistent with an I2C/SPI-style
programming bus (e.g. SDA+SCL idle high), matching the "JPRG" (programming)
silkscreen and adjacent supervisor IC `21_U2` (`MDC1103S`), rather than an
async serial console.

Reproduction: adapter GND→JPRG1 position 2; RXD→candidate pin;
`stty -F /dev/ttyUSB1 <baud> cs8 -cstopb -parenb raw`; capture during
power-cycle.

## 10e. Public research map for the granite2 platform (2026-10-28)

The Sifter's compute unit targets `granite2v8-sifter` — same Lexmark granite2
platform family as the MC3224i printer (Pwn2Own 2021) researched publicly:

[O] NCC Group part 1 (nccgroup.com/research/bypassing-software-update-package-
encryption-extracting-the-lexmark-mc3224i-printer-firmware-part-1):
- SoC: Marvell 88PA6220-BUX2 ("Pegmatite", ARMv7; /proc/cpuinfo says
  "Marvell Pegmatite (Device Tree)"); machine model "mv6220 Lionfish".
- **Console UART lives on a PCB connector labeled `JRIP1`**, 115200 baud;
  full boot log observable (TIMH/AVS/DDR init → U-Boot 2018.07 → kernel
  4.17.19-yocto; earlycon at MMIO 0xd4030000).
- **UART RX pin disabled on production units** ("did not appear to be
  enabled... possibly disabled through e-fuses... or a zero-ohm resistor may
  have been removed") → boot log readable, no interactive shell.
- Flash layout (NAND on printers): TIMH / OBMI / OSLO(U-Boot) / TRDX(kernel+
  dt) / UBI volumes incl Base(squashfs), Engine, InternalStorage, Kernel;
  U-Boot bootcmd uses sha256verify + cramfsload /main.img script.
- Firmware extraction done by chip-off NAND (TSOP-48) — unencrypted at rest
  on that generation.

[O] haxx.in "Retrofitting encrypted firmware is a Bad Idea™" (2024-09-23) +
"Let's PWN WTM!" (2024-09-27), by blasty:
- Newer granite2 firmware encrypts rootfs; key unwrapped at boot from Marvell
  WTM security co-processor ("Wireless Trusted Module", internal platform
  name mckinley5) via netlink → wtm-client.ko → wtm-controller.ko → MMIO.
- WTM command table includes `wtm_oem_jtag_key_bind`, `wtm_oem_jtag_key_
  verify`, `wtm_otp_*`, `wtm_set_jtag_permanent_disable`,
  `wtm_set_temporary_fa_disable` → **JTAG is key-provisioned and fusable**;
  debug access deliberately locked on production hardware.
- Rooted device = key oracle: replaying netlink unwrap messages yields the
  AES rootfs key for ANY firmware version; tools:
  github.com/blasty/lexmark (fw_decrypt.py, rootfs_decrypt.py).
- WTM runs a full Linux kernel itself; follow-up post achieves arbitrary WTM
  command issuance / RCE from a rooted AP via custom kernel module.

[I] Implications for the Sifter:
- Silence on JPRG1/JCFT1 pins during boot is consistent with platform norms:
  consoles are semi-disabled on production granite2 hardware, and JTAG is
  OTP-locked.
- Most practical firmware-access path may be SOFTWARE (rooted userland via
  skills/EWS per §10b/§10c); hardware UART RX and JTAG routes are hardened.

## 10f. Regulatory identification resolved (2026-10-28)

[O] Regulatory label on the Sifter: **"Contains FCC ID: TLZ-CM467"** +
**"Contains IC: 6100A-CM467"** = AzureWave AW-CM467, an IEEE 802.11 a/b/g/n/ac
+ Bluetooth 5.0 combo module, Single Modular Approval (grant 2021-12-20;
C2PC 2024-09-09), grantee AzureWave Technologies (TLZ). fccid.io/TLZ-CM467.
"Contains FCC ID" phrasing = host label citing the module's
modular approval.
- The Compute 550 host itself has NO own FCC ID — consistent with Class A
  sDoC (user guide carries only a Part 15 compliance statement; board
  silkscreen has no FCC marking; Lexmark's own grantee IYL has no filings
  after 2018).
- Module identity matters for later software work: AW-CM467 radios are
  MediaTek MT7663-family → mt76/vendor driver territory once we have
  Linux userland access.
- Module-level FCC internal photos show the module only, not the host board
  → no console-layout intelligence from this filing.

[O] Label also reads **Machine type: 8085-001** and **P/N 10U0900-003**
(unit assembly; board is 10U9020 REV 4). Machine type **8085** differs from
the published Compute 500/550 docs (machine type 8080) — no public Lexmark
documentation exists for 8085 (publication/support portals searched) → the
Sifter's compute unit is an unpublished OEM/custom SKU. Public docs keyed to
8080 apply only loosely; firmware/build targets may differ.

## 10g. CONSOLE FOUND — JRIP1 pin 2, 115200, TX-only (2026-10-28)

[O] After ruling out JPRG1 (programming bus) and JCFT1 (pin1 = reset line,
break-proven), the silkscreen **JRIP1** was located near the main SoC
(right side, heatsink), 4 positions, with an unidentified female-adapter
harness plugged in. Adapter GND → JRIP1 pin 4 (continuity-verified GND),
adapter RX → pin 2: **full boot log captured at 115200 8N1**
(`device/uart/boot-full-jrip1-pin2.log`, 40,648 bytes). Pin 1 silent;
pins 2 = TX out. Console input: newlines produce no response and no serial
getty appears in the log → **TX-only**, matching NCC's production-granite2
finding (RX disabled via efuse/removed resistor).

[O] Boot log contents (highlights):
- Boot ROM "Si Gr2-RevC1 3.3.22-6h" (build 2025-08-07?), COMMIT=584b6b8,
  AVS/efuse init, DDR4 800MHz 4x8 8Gbit (ref 10U9010), "Launch AP Core0".
- **U-Boot 2022.01** (built 2026-06-12), `pegmatite-u-boot`, DRAM 3 GiB,
  mv_sdh 0/1/2, panel-eeprom probes fail (no panel on Sifter).
- Kernel cmdline: `earlycon=early_pxa,mmio32,0xd4030000
  console=ttyS0,115200n8 swiotlb=32768
  systemd.machine_id=d8bcba10abc99f95bf6aa1623d2d16e3` + dm-verity:
  `verity-p3 ... /dev/mmcblk1p3 ... sha256 17b6449671ef903494f56b2317267e81
  35bea8b2c68c7706afb50979c5608bcb` root=/dev/dm-0 BOOT_PARTITION=5.
- UARTs: ttyS0 @0xd4030000 (console), **ttyS1 @0xd4017000** (second UART,
  purpose unknown), /dev/ttyLPP0 (panel console). MDCIF device-control
  server listens on **TCP port 50800** (joins 9002/21586/21587 in the
  service inventory).
- systemd services incl. Edge IoT, Edge Device Web Services (EWS), Edge
  Watchdog, Docker Application Container Engine; Sifter-specific init
  ("Expand docker-seed partition to fill eMMC (sifter devices only)").
- Runtime errors visible at boot: `scan_queue_prune,394:ERROR:Scan0..9 Q
  prune(side:0, page_id:0) not in any Q` and `stmotor_BaseFreq: PWM_M ratio
  obtained is 0... force to 1` / `pwm pwmchip0: Bad values - c0:0 c1:400`.

[O] **Stall behavior + attempted recovery (2026-10-28, live-observed)**: when a
job stalls at ~10 cards (device healthy but idle, portal stuck "in progress"),
opening/closing the ADF back cover produces motion ("it plays") but per the
owner the job **does not actually continue** — the reliable recovery is
**cancelling the job and starting a new one**. Console captured the toggle
verbatim: `MDCIF: At 00390.759895 - (ADF BACK COVER OPEN)` /
`MDCIF: At 00392.550611 - (ADF COVER CLOSED)`. Establishes that MDCIF reports
sensor-state transitions on the console at runtime (cover sensors at
minimum), timestamped by device uptime.

[I] Uses from here:
- Live runtime observability: console feed during jobs will show the
  stall failure mode's internal state (scan pipeline, motor driver, cloud
  orchestrator complaints) without any device modification.
- ttyS1 is a second serial port worth probing later.
- Console input remains available via the software route; hardware RX
  enable would require locating the efuse/zero-ohm resistor — not needed
  if userland access lands first.

[O] **Dual-instrumented stall capture (2026-10-28 ~15:04)** — console stream +
EWS settings polled every ~14s (`device/uart/ews-job-timeline.jsonl`,
poller `tools/ews-poll.py`, auth per §3). Job scanned cards then stalled:
- AdfFrontSideCount/AdfBackSideCount 3919 → **3940 at 15:04:06** (job active;
  note +21 delta for a reported single card — counter likely ticks per
  sensor/roller event or includes backlog accounting), then **frozen at 3940
  across 5 consecutive polls (75s+)** during the stall.
- `ConnectedToHub: true` and `NetworkOnline: true` in EVERY sample including
  during the freeze → **stall is not connectivity**.
- CPULoad ~0.83–1.0, CurrentProcesses ~440, FreeRAM ~2.95GB all stable →
  **stall is not a device crash/resource event**.
- Console emitted zero bytes through scan + stall → no kernel/driver events;
  deadlock is in the application/orchestration layer (container logs needed
  → software route).
- EWS auth notes: http://<LAN_IP>/webservices/* 301→ https (self-signed;
  use -k / unverified context); Basic auth `optra:<devicePassword>`;
  webserver is SLOW (~6.6s/request).
- Settings/all also exposes lifetime telemetry: AdfFront/BackSideCount,
  SerialNumber 808563180009W (8085 machine type in serial), ScopeId,
  SkillsRunning, IotedgeVersion, eMMC wear, WiFi link stats, and sensitive
  material (Wireless_PSK, HostAP_PSK, TPM_EK, EWS_Password_Hash) — keep
  raw dumps local only.

## 11. Reference files

- `reference/optra-compute-ug.pdf` — Optra Compute user guide (endpoint table,
  button/light behaviors incl "Pulling firmware" LED state)
- `reference/optra-ug.pdf` — generic Optra device user guide
- `device/identity.json`, `device/external-urls.json`,
  `device/external-urls-during-job.json`, `device/device-logs.bin` (encrypted)

## 12. Live event bus + scan-image pipeline (2026-10-30)

### Channels

- **9002/tcp** — WebSocket carrying MessagePack binary frames. Handshake
  succeeds on any path (`/`, `/ws`, `/events` all return `101`). No auth. [O]
- **21587/tcp** — raw TCP, same MessagePack payloads as 9002; sends during
  scan activity. An idle receive-only probe got zero bytes, so “server speaks
  first” is activity-dependent, not a banner. No auth. [O]
- **21586/tcp** — accepts TCP and stays silent indefinitely (15 s with no
  bytes during an active scan). Any input closes it within ~5 ms: every byte
  value `0x00`-`0x0f`, `A`-`Z`, `{}[]<>`, `0x7f`, `0xff`, plus HTTP requests,
  a TLS ClientHello, and MessagePack payloads. Multi-byte payloads that leave
  unread data produce a TCP reset instead of a clean FIN; UDP is silent. No
  handshake found - behaves like an internal consumer that drops foreign
  input rather than a service with a discoverable protocol. [O]
- **50800/tcp** — MDCIF binds at boot (`MDCIF: At 00009.177602 - Listening for
  TCP connection on port 50800`); connections from the LAN are refused while
  the other tested ports accept, which is consistent with loopback or
  container-network binding [I]. HTTP is unproved. [O]

- While the front door is open the device reports `ERR109: Front door is
  open`, clears `lastJobId`/`lastJobState`, and the bus goes silent - the
  pipeline stops at the physical interlock. [O]

### Message format

Envelope is a three-element array: `[2, "<event>", [<payload>]]`. Events seen:
`nodeChanged`, `nodeAdded`, `nodeRemoved`. The payload maps node path → body.

```
PageQueue/<id>/Front|Back/state      Scanning -> Safe -> Ejected
PageQueue/<id>/Front|Back/Image      geometry + handle (see below)
PageQueue/<id>/foil                  Detected | NotDetected
PageQueue/ready                      bool
Status/SideCountPermanent/adfFront|adfBack   lifetime sheet counters
nodeAdded / nodeRemoved              PageQueue/<id> and child node "eject"
```

Image node as emitted for the front side of a sheet:

```json
{"composition":"Rgb24","handle":0,
 "mediaWindow":{"x":-900.0,"y":0.0,"w":1800.0,"h":2020.0,"xRes":600.0,"yRes":600.0},
 "outputCanvas":{"x":-420.0,"y":-75.0,"w":870,"h":1170,"xRes":300.0,"yRes":300.0},
 "compression":"Jpeg"}
```

The back side is identical except `outputCanvas.x = -450.0` and `handle = 1`.
There is no byte count, path, URL, or payload anywhere in the stream — only a
handle into the device's own image store. [O]

### Card lifecycle (60 s capture during a live run)

494 messages across 25 sheets (page ids 19-67, odd only - ids advance by two per
sheet). Events: nodeChanged 445, nodeAdded 25, nodeRemoved 24. Per sheet:

```
nodeAdded    ["PageQueue", "<id>", "eject"]
nodeChanged  Front/state Scanning -> Back/state Scanning -> foil -> Safe x2
             -> Front/Image leaves -> Back/Image leaves -> Ejected x2
nodeRemoved  ["PageQueue", "<id>"]
```

Image fields arrive as individual leaf updates (composition, handle,
mediaWindow/x..yRes, outputCanvas/x..yRes, compression), ~20 messages per sheet.
PageQueue/ready reads true between sheets; Status/SideCountPermanent/adfFront and
adfBack increment by one per side (5618 -> 5637 over the capture).

Channel split: raw TCP carried 345 messages, WebSocket 149 - a late WebSocket
connection misses earlier frames but sees everything after it attaches. [O]

Capture: device/bus-capture-20261030c.jsonl

### Vision API (port 5000) serves no images

`/openapi.json` lists exactly four routes: `GET /ram`,
`POST /sifter/initialize`, `POST /sifter/recognize_card`, `POST /sifter/reset`.
`CropInfo` is `{x,y,width,height,score}` only; `/ram` returns
`{"ram_usage":29.5}`. Eighteen guessed image routes (`images`, `image`, `scans`,
`scan`, `capture`, `frame`, `last_image`, `debug`, `health`, `metrics`,
`status`, `camera`, `snapshot`, `photo`, `files`, `storage`, `media`) all return
`404 application/json`. [O]

### Portal and cloud serve thumbnails only

Batch items carry exactly one image field:

```
imageUrl = https://ql-api.tcgplayer.com/images/<batchId>/<batchItemId>/thumb.jpg   (446x600)
```

Tested in an authenticated seller tab against a real item: `full.jpg`,
`original.jpg`, `image.jpg`, `large.jpg`, `thumb@2x.jpg`, `thumb.png`,
extensionless directory path, `full`, and `?w=870` all return **404**; only
`thumb.jpg` returns 200 (85,842 bytes). `/batch/<id>/scans`,
`/batch/<id>/images`, and `/scans?batchId=` also return 404. [O]

The thumbnail's aspect ratio (446/600 = 0.7433) matches the bus's output canvas
(870/1170 = 0.7436), so the portal image is a ~0.5× downscale of the JPEG the
device produces — not a separate capture path. [I]

The device's own reachability list includes `https://bucket.optra.com:443`: an
S3 bucket behind CloudFront that answers anonymous requests with
`403 AccessDenied`. Keys are not guessable and listing is denied. [O]

### Conclusion

No owner-reachable surface returns scan image bytes today. The pixels exist on
the device behind an internal handle and in vendor object storage behind
credentials; every owner-facing interface exposes metadata only (geometry,
foil detection, counters). Full-resolution retrieval would require code
execution on the device to reach MDCIF or its image store, a trusted TLS
position to capture the upload (the device trusts Lexmark/Azure roots), or
vendor storage credentials. [I]

### Artifacts

- `tools/bus-probe.py` — read-only capture tool for both channels.
- `device/bus-capture-20261030.jsonl` — 60 messages from a live job.
- `device/bus-capture-20261030b.jsonl` — 74 messages across both channels.

## 14. Boot network capture & settings survey (2026-11-24)

### Method: gateway-side capture
Captured from the UniFi gateway (`10.0.0.1`, SSH root) with tcpdump — no agent
or change on the device itself. Hardware-offload caveat applies: the gateway
ASIC switches established flows past the CPU, so only NEW flows are visible;
a controlled reboot (all flows new) gives the complete picture. Three
captures ran pre-reboot: DNS text log, conntrack NEW events, full pcap
(`/root/sifter-boot.pcap`, copied off-box for parsing). SLL2 linktype puts a
20-byte header before each frame; DNS QNAME/CNAME chains extract cleanly in
~40 lines of pure Python (struct + name-pointer decompression);
`strings(1)` will NOT find TLS SNI.

### What a clean boot actually does [O]
| Phase | Destination |
|---|---|
| DHCP | LAN gateway |
| NTP | `time3.google.com` (`216.239.35.8`) |
| Connectivity check | `www.microsoft.com` via Akamai (`e13678.dscb.akamaiedge.net` → `2.18.202.94`) |
| Name browsing | LLMNR multicast `224.0.0.252:5355` |
| Control plane | **persistent TLS/MQTT to `optra-release.azure-devices.net`** (`40.71.14.132:443`, Azure IoT Hub eastus) |

**A clean boot performs NO firmware check at all** — zero packets to
`bucket.optra.com`, no SWUpdate CDN traffic, no hit on the armed
`Pull_FW_URL` proxy across two boots and a setup-button tap.

Conclusion [I→effectively O]: updates are CLOUD-PUSHED over the IoT Hub
connection (device twin desired properties / direct methods); the device only
pulls bytes when told to by the cloud. This explains every prior negative
result: reboot wipes `Pull_FW_URL` before any local check could use it,
the setup button doesn't trigger a pull, and no hidden EWS update endpoint
exists — the trigger was never local.

Practical consequence: the `Pull_FW_URL` redirect is a PASSIVE STAKEOUT.
Pass-through proxy armed on `10.0.0.10:8888` forwarding unchanged to
`https://bucket.optra.com`, logging method/path/headers/upstream status as
JSON lines (`/tmp/pullfw-proxy.log`). Verified end-to-end with a real 403
passthrough from the bucket. NEVER fabricate firmware bytes in the listener —
serve real pass-through or nothing so a genuine OTA still succeeds.

### Settings survey — full 121-key live dump [O]
Re-dumped `/webservices/settings/all` post-boot (fw 3.5.7):

- **No update-channel / maintenance-window / update-policy key exists** in the
  settings surface → that configuration lives entirely cloud-side (IoT twin),
  corroborating the capture conclusion above.
- `FirmwareStatus` is an enum (`Ready (0)`) — expect Downloading/Installing
  states to appear during a real OTA; poll it during the stakeout.
- `IotedgeVersion = 1.6.8` reported separately from `FirmwareVersion`.
- Device exposes its Azure DPS `ScopeId` (`0ne00197463`) and a hashed
  `MachineID` via settings — tenant identifiers, kept out of the public repo.
- **NEW LEVER — device-wide HTTP proxy**: `ProxyScheme`, `ProxyAddress`,
  `ProxyPort`, `ProxyUsername`, `ProxyPassword` keys exist and are writable
  via the settings API (currently all empty/default). Pointing the device at
  a local pass-through proxy would expose EVERY outbound hostname via CONNECT
  headers (TLS content stays pinned to Lexmark/Azure CAs — observation only,
  no MITM). UNTESTED; strongest next experiment if we want endpoint visibility
  beyond boot. Same restore-original-value discipline as Pull_FW_URL.
- Full key list archived locally (`device/settings-all-20261028.json` +
  fresh dump in session scratch) — contains credential hashes; not published.

### Stakeout state at close of session
- Device online (Wi-Fi `10.0.0.66`), fw 3.5.7, FirmwareStatus Ready,
  ConnectedToHub True.
- `Pull_FW_URL = http://10.0.0.10:8888/fw/test` re-armed post-boot.
- Proxy live on `:8888`; gateway watchers still running (DNS log + full pcap).
- Original value of `Pull_FW_URL` is EMPTY STRING — restore with
  PUT `{"Pull_FW_URL": ""}` when the experiment ends, verify by readback +
  FirmwareStatus Ready.

### Addendum: device-wide HTTP proxy — CONFIRMED LIVE (2026-11-24, same night)

PUT `ProxyAddress=<workstation-lan-ip>` / `ProxyPort=8889` via the settings
API took effect IMMEDIATELY — no reboot. Sequence observed:

1. Web service bounced for ~60 s after the PUT (ports 443/8080 refused, then
   timed out briefly) — benign, self-recovered.
2. Within 90 s the device tunneled through the proxy:
   `CONNECT www.microsoft.com:443` (NCSI check) and
   `CONNECT optra-release.azure-devices.net:443` ×3 (control plane re-dials).
3. Device stayed healthy throughout: `NetworkOnline true`,
   `ConnectedToHub true`, `FirmwareStatus Ready`.

Result: **every outbound hostname the device dials is now observable live**
via CONNECT log lines (`/var/log/sifter-fwproxy.log`), while TLS content
stays end-to-end (CA-pinned, no MITM). The IoT Hub control plane honors the
device-wide proxy — so when Roca cloud-pushes an OTA, the firmware CDN
hostname will appear in the CONNECT log even before any byte is pulled.

Deployment hardening: proxy promoted from an ad-hoc process to a supervised
systemd unit (`sifter-fwproxy.service`, `Restart=always`) since the device's
entire cloud path now depends on it. Script at
`/usr/local/sbin/sifter-fwproxy.py`, log at `/var/log/sifter-fwproxy.log`.

Overnight stakeout now has THREE independent tripwires:
1. `Pull_FW_URL` redirect proxy (:8888) → exact object path of the pull.
2. Forward-proxy CONNECT log (:8889) → every hostname dialed, incl. CDN.
3. Gateway pcap/DNS/conntrack watchers → ground truth even if proxies die.

Restore procedure when done: PUT `{"ProxyAddress": "", "ProxyPort": ""}`
(factory defaults), verify readback + `ConnectedToHub true`.

## 15. Overnight stakeout results (2026-11-24)

The three tripwires ran a full night (~19 h). No OTA fired — `FirmwareStatus`
stayed `Ready`, zero firmware-CDN pulls, the `Pull_FW_URL` redirect proxy saw
nothing but our own sanity probes. But the proxy-arm event itself triggered a
**one-time cloud-init sync burst** that revealed the application distribution
layer:

### 15.1 The burst (03:24–03:26 UTC, exactly at proxy-arm)

Arming the device-wide proxy restarted the device's network stack, which made
the IoT Edge runtime perform a full deployment sync it never does at boot:

| Endpoint | Role | Traffic |
|---|---|---|
| `registry.gitlab.com` + `gitlab.com` | **Roca's private container registry** — IoT Edge module images | ~375 KB in (API/manifest scale) |
| `mcr.microsoft.com` | Microsoft Container Registry (base images) | ~300 KB in |
| `secretsmanager.us-east-1.amazonaws.com` | AWS Secrets Manager | small |
| `c3q7297lxqxja3.credentials.iot.us-east-1.amazonaws.com` | AWS IoT credential provider | small |
| `a2rtvkqn1uafrt-ats.iot.us-east-1.amazonaws.com:8883` | **AWS IoT Core MQTT — second control plane** | small |
| `apis.us.iss.lexmark.com` | Lexmark intelligent-services API | small |

Manifest-scale volumes only (~700 KB total): the runtime verified module
assignments and digests but pulled no image layers (already cached on device).

### 15.2 Architecture picture

The device runs **dual control planes**: Azure IoT Hub
(`optra-release.azure-devices.net`, persistent MQTT/TLS) *and* AWS IoT Core
(MQTT :8883, reconnects alongside the Azure hub — observed together at
11:06 UTC). Application code ships as **IoT Edge container modules from a
private GitLab registry**, not from `bucket.optra.com`. The Lexmark CDN is
therefore likely reserved for full firmware images, while day-to-day app
updates flow through the container registry.

### 15.3 Proxy coverage gap

Only the Azure hub, Microsoft NCSI check, and AWS Secrets Manager honored the
device-wide proxy (`CONNECT` log). The **IoT Edge container runtime bypassed
it entirely** — direct connections to GitLab/MCR despite
`ProxyScheme=http`, `ProxyAddress`, `ProxyPort` all set. Its proxy config
lives in `/etc/aziot/config.toml` (needs shell access; unreachable via the
settings API). Consequence: registry hostnames are visible via gateway
DNS/SNI, but registry request paths are not capturable without either shell
access or a trusted CA on device (TLS rejects non-Lexmark CAs).

### 15.4 Burst trigger

The sync fired exactly once, at network reconfiguration — not at boot, not
periodically. Re-triggerable in principle by toggling the device proxy
off/on; each toggle costs a ~60 s web-service bounce.

## 16. Scan-image upload destination + job-pause behavior (2026-11-24)

Two observations from a live job day:

**Scan images upload to TCGplayer's own S3 bucket** — during active scanning
the proxy CONNECT log recorded TLS connections to
`tcgplayer-ims-image-upload-bucket-prd-us-east-1.s3.us-east-1.amazonaws.com`.
This confirms scan imagery leaves the device for AWS us-east-1 during jobs,
over a path that honors the device-wide HTTP proxy setting (i.e. the web
service stack, not IoT Edge). Only two connections for ~30 scanned cards ⇒
connection reuse or batched uploads.

**Jobs pause and resume without owner input, device stays healthy** — a job
resumed on its own after hours idle, scanned ~30 cards, then paused again;
throughout both states the device reported hub-connected / online /
firmware-ready via its local status API. Vendor support history for this
product line indicates stall/pause symptoms of this shape originate in the
backend job orchestration (recognition counters advancing while results fail
to persist), not in device or LAN faults.
