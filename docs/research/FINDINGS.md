> Public copy of the local findings, with owner/device identifiers removed. Captures and vendor PDFs referenced below are retained locally, not included here. These are research observations, not an independently validated API specification. See [current device findings](../device-findings.md) for proxy cleanup and later observations.

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
| Serial | <DEVICE_SERIAL> | [O] cloud + device |
| Azure identity | thingName sifter-<DEVICE_SERIAL>, DPS scope <DPS_SCOPE> | [O] |
| Build target | granite2v8-sifter (OEM_ID 2, Family Roca, Series TCGPlayer) | [O] device settings API |
| **Firmware** | **3.5.4** | [O] device settings API |

## 2. Network presence (Owner's LAN)

- Wired: **<DEVICE_LAN_IP>** (MAC <DEVICE_MAC>, Lexmark OUI; mDNS `optra-<DEVICE_SERIAL>`)
- Wireless: **<DEVICE_LAN_IP>** (MAC <DEVICE_MAC>)
- Both serve the same EWS on :443 — "TCGplayer Device Setup" (Vite SPA),
  self-signed cert CN=optra-<DEVICE_SERIAL>. Server banner: `webserver`.
- Setup-mode AP portal mirrors EWS at http://172.16.131.2/setup (advanced
  network config at http://172.16.131.2). [O] Roca setup docs
- Rate limiter: ~8 rapid requests -> 429. Space probes 3-5s. [O]

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
GET  /images/<batchId>/<batchItemId>/thumb.jpg   446x600 JPEG, observed rendition
                                                  (full/original/large probes failed)
```
No directory listing anywhere; batchItemIds are non-sequential.
NO remote device-log/diagnostics endpoints on ql-api (404s). [O]

## 5. Data harvested -> this folder

- `batch-<BATCH_ID>-scans.json` — full scan list snapshot (501 items) + batch meta
- `manifest.csv` — 501 rows: name/set/number/condition/printing/language/
  confidence/pricing/marketPrice/bin/imageUrl per scan
- `images/` — 501 scan JPEGs (48MB), all verified valid 446x600
- Batch <BATCH_ID> ("<BATCH_NAME>"): $71.45 total pricing, matched entries reported confidence=Good,
  Aether Revolt, 0 duplicates
- Second job batch **<SECOND_BATCH_ID>** observed live (foil sift); not harvested yet

## 6. Vendor infrastructure map

| Endpoint | Purpose | Access |
|---|---|---|
| portal.optra.com | Lexmark Optra Portal (device mgmt) | auth required; GraphQL API host injected post-login; CF blocks anon POST |
| docs.optra.com | Optra Edge Portal documentation (devices, skills, workflows, admin) [O 2026-11-23] | public |
| optra-release.azure-devices.net | Azure IoT Hub | device-only |
| global.azure-devices-provisioning.net | Azure DPS | device-only |
| optrarelease.azurecr.io | Azure Container Registry (skill images) | anon pull DISABLED (401 even per-repo) |
| bucket.optra.com | S3: **firmware downloads on update** [O user guide] | listing 403; object ACLs unknown |
| logsene-journald-receiver.sematext.com | app log upload / remote diagnostics | device-only |
| mcr.microsoft.com + *.blob.core.windows.net | IoT Edge base images + ACR image deltas | public |

## 7. Firmware availability

- No public firmware download was found in this investigation.
  Firmware is portal-managed OTA; delivered from bucket.optra.com on update,
  skill containers from optrarelease.azurecr.io. [O docs + user guide]
- "granite2v8" build target: zero public hits.
- LexmarkVentures GitHub has only skill SDK examples, no device firmware.
- Community RE of the Sifter: none found (hardware shipped Sept 2026).

## 8. MITM capture experiment (2026-10-24) — tested, NOT viable for jobs

- Device honors `PUT /webservices/proxy` (port must be a STRING). Intercept
  mode rejected (`tlsv1 unknown ca` — test CA not trusted);
  pass-through mode (`--ignore-hosts '.*'`) tunnels fine.
- Applying the proxy bounces the device (~1min EWS + cloud outage, self-recovers).
- Even sequenced correctly (proxy → stable → job start), the job died ~2min in
  (white flashing light, 0 cards). The reason for the job failure was not isolated.
- Yield: new hosts `secretsmanager.us-east-1.amazonaws.com` (device pulls
  runtime secrets — likely ACR creds/job tokens) and `apis.us.iss.lexmark.com`.
- Logs in `mitm/`.

## 9. USB device port and board survey (2026-10-27)

Full details in [BOARD-NOTES.md](BOARD-NOTES.md). Summary:

- Rear USB-B (device) port enumerates as a Lexmark composite USB device
  (VID `043D`, PID `0122`): HID + vendor-specific interface named **"Scan"**
  (bulk OUT `0x02` / IN `0x82`) + USB printer class ("Print"). No CDC network
  gadget — the documented EWS-over-USB address is absent on fw 3.5.4.
- Passive captures (Linux usbmon + interface claims, idle and during a live
  job) show the port is inert during normal operation; data requires actively
  driving the vendor protocol. Raw `/dev/usb/lp0` writes are accepted.
- Network surface: only 80/443 open; no PJL/IPP/LPD/SSH; unknown HTTP paths
  hit the SPA catch-all. Attack surface is the authenticated
  `/webservices/*` API.
- Mainboard photographed: **Lexmark P/N `10U9020 REV 4` (`YYZ00C`)**. Key ICs:
  Marvell 88PA6270 ("Pegmatite") quad-core ARMv8-A SoC (`16_U1` under heatsink),
  4 GB DDR4 SDRAM (`4× Nanya NT5AD1024M8C3-HR`, `16_U2`–`16_U5`), 16 GB Kioxia
  eMMC 5.1 (`THGAMVG7T13BAIL`, `16_U6`), Infineon `SLB9672` TPM 2.0 (`U3`),
  Marvell `88EC068-NNB2` Gigabit Ethernet PHY (`19_U1`), AzureWave `AW-CM467`
  Wi-Fi 5 / BT 5.0 module (`36_U5`, FCC ID `TLZ-CM467`), TI `TLV320DAC3100`
  audio DAC (`U1`), ST `24C04WP` I²C EEPROM (`U101`), `MDC1103S` reset
  supervisor (`21_U2`), TI `TPS56637` (`27_U1`) and `TPS65266` (`23_U1`) buck
  converters, rechargeable RTC coin cell (`B1`), 4-pin `JRIP1` UART console
  header (pin 2 TX @ 115200 8N1, pin 4 GND), and unpopulated 6-pin `21_JPRG1`
  programming header.

## 10. Routes to firmware bits (remaining)

1. **Physical** — UART pads / eMMC dump on the Compute 550 board; read access and secure-boot behavior remain unverified on this board.
2. **Ask** — Roca support (support@rocarobotics.com) or Lexmark Optra support
   (optra.techsupport@lexmark.com) for a firmware image.

Note: Roca T&C contains a software reverse-engineering restriction clause.

## 10. Reference files

- `reference/optra-compute-ug.pdf` — Optra Compute user guide (endpoint table,
  button/light behaviors incl "Pulling firmware" LED state)
- `reference/optra-ug.pdf` — generic Optra device user guide
- `device/identity.json`, `device/external-urls.json`,
  `device/external-urls-during-job.json`, `device/device-logs.bin` (encrypted)

## 11. Live event bus and the scan-image pipeline (2026-10-30)

- Two unauthenticated MessagePack channels stream the scan pipeline's node
  graph: **9002/tcp** (WebSocket, handshake succeeds on any path) and
  **21587/tcp** (raw TCP; sends during scan activity, no unsolicited
  banner). Same payloads on both. [O]
- Envelope `[2, "<event>", [<payload>]]`; events `nodeChanged`, `nodeAdded`,
  `nodeRemoved`. Nodes observed: `PageQueue/<id>/{Front,Back}/{state,Image}`,
  `PageQueue/<id>/foil`, `PageQueue/ready`,
  `Status/SideCountPermanent/{adfFront,adfBack}`. [O]
- Page states run `Scanning` → `Safe` → `Ejected`; foil reports
  `Detected`/`NotDetected` before recognition runs. [O]
- The `Image` node carries geometry and a handle only — no bytes, path, or URL:
  `mediaWindow` 1800×2020 @ 600 dpi Rgb24 in, `outputCanvas` 870×1170 @ 300 dpi
  Jpeg out, `handle` 0 for front and 1 for back; the handle is a per-side
  slot index reused for every page, not a durable image id. [O]
- **21586/tcp** accepted connections but stayed silent in the observed window;
  tested inputs caused closure within ~5 ms. No handshake was established. [O]
  An internal consumer is a hypothesis; authentication, framing and owner
  process remain unknown. [I]
- MDCIF announces TCP **50800** at boot; prior LAN connections were refused. [O]
  Loopback/container binding, service state and filtering remain unresolved;
  the refusal does not prove a binding address. [I]
- The Vision API on port 5000 has exactly four routes and returns no images;
  `CropInfo` is four integers plus a score. [O]
- Portal batch items expose one image field, `thumb.jpg` at **446×600**. Ten
  larger-variant guesses (`full.jpg`, `original.jpg`, `large.jpg`,
  `thumb@2x.jpg`, extensionless paths, query sizes) return 404, as do
  `/batch/<id>/scans` and `/batch/<id>/images`. [O]
- The thumbnail's aspect ratio matches the bus's output canvas ⇒ the portal
  image is a ~0.5× downscale of the device JPEG, not a separate capture. [I]
- `bucket.optra.com` is an S3 bucket behind CloudFront; anonymous access returns
  `403 AccessDenied`. [O]
- **Qualified conclusion:** no tested local endpoint returned full-resolution
  image bytes; portal thumbnails are exportable. Image persistence, handle
  ownership and a supported full-resolution retrieval route remain unresolved. [O/I]

## 12. Complete UART and diagnostic review

The [October 30 diagnostic research](diagnostic-research-2026-10-30.md) includes
the complete per-line boot report, settings/service map, access prerequisites,
and USB/reset analysis.
It covers 103,380 original physical lines, with exact duplicate-range mappings
and 732 reconstructed UART lines. Most source lines are blank scrollback.
Raw captures remain private under `device/`; only redacted derivatives are published.

Details, reproduction steps, and the full port table: [`docs/surfaces.md`](../surfaces.md).
Capture tool: [`tools/bus-probe.py`](../../tools/bus-probe.py).

## 13. Optra Edge Portal docs & 2026-11-23 UART boot diff (2026-11-23)

### Optra Edge Portal documentation (`docs.optra.com`)

Sources: `https://docs.optra.com/devices/overview/`, `enroll-device/`, `maintenance-window/`, `troubleshooting/`, `skills/overview/`, `skills/add-skill/`, `skills/privileges/`, `skills/inputs-and-outputs/` (copyright 2026 Lexmark Ventures LLC).

- **Firmware updates & recovery gap `[O]`:** Firmware delivery is documented strictly as portal-managed OTA — either triggered manually from the device detail view or applied automatically during 2-hour organization/device Maintenance Windows (firmware update first, then skill sync). Two channels exist: `stable` (all organizations) and `early` (requires an org-level feature flag). `Troubleshooting Devices` lists no downloadable `.swu` package, offline/USB recovery path, or engineering/debug image program; failed updates only instruct retrying from the portal and checking `Device Logs`.
- **Enrollment & tenant lock-in `[O]`:** Standard Optra devices use a 13-character serial starting with `8080` and require pressing the physical setup button (5–7 minute enrollment window) while claiming the device at `portal.optra.com`. Attempting to enroll an already-claimed device returns `"Device is not claimable"`, confirming OEM units enrolled under Roca/TCGplayer's tenant cannot be self-enrolled into another Optra Portal organization unless unenrolled `[I]`.
- **Portal EWS tunnel & Skill Web UI `[O]`:** The portal's EWS button opens a secure reverse tunnel to the device's on-board EWS that expires after 1 hour. Skill `Web UI` binds `{exposedPort}/tcp` (optionally `HostIp: 127.0.0.1`) and proxies browser access through the portal.
- **Skill container runtime & Docker `HostConfig` mechanics `[O]`:**
  - `Docker Image` skills (Docker Hub, Azure ACR, or private registry; AWS ECR unsupported) support the full privilege set; `Docker Compose` skills (`.tgz` uploaded in the portal) support **only** `Env` and `Web UI`.
  - Skills join the `azure-iot-edge` Docker network (`NetworkingConfig.EndpointsConfig['azure-iot-edge'].Aliases`).
  - `Port Bindings` explicitly forbid host ports **`22, 53, 80, 443, and 8080`** (matching the on-device EWS / `SettingsPort8080` ports).
  - `Removable Media` mounts `/run/removable_media:/media:shared` (correlates with the `Auto Config & Mount extended storage` systemd unit `[I]`).
  - `Volumes` create named Docker volumes (`type: volume`, alphanumeric name, optional `size`); `Tmpfs` and `SHM Size` map to Docker `type: tmpfs` and `HostConfig.ShmSize`.
  - `Host Networking` (`NetworkMode: host`) and `NET_ADMIN` (`CapAdd: ["NET_ADMIN"]`) require org-level feature flags from Optra support.
  - Hardware privileges documented: `Sound` (`/etc/asound.conf:ro`, `/dev:/dev:ro`, `/dev/snd`, `c 116:* rmw`), `Connected Cameras` (`c 81:* rmw`), `USB Serial Converters` (`c 166/167/188/189:* rmw`), plus model-gated privileges for Vision/CX2000 devices (`GPIOs`, `HDMI`, `IR`, `Host Video Libraries`, `LED Control`).
  - Skill inputs are pushed via Azure IoT module twin desired settings; outputs are emitted as JSON over Azure IoT messages.
  - Full privilege-to-`HostConfig` summary for the exporter draft: [`skills/sifter-export/PRIVILEGES.md`](../../skills/sifter-export/PRIVILEGES.md).
- **Public prior-art sweep `[O]`:** Searches across `support.lexmark.com`, `docs.optra.com`, `support.rocarobotics.com`, GitHub, Reddit, and hardware teardown sites found no public Optra Compute 550 / Roca Sifter firmware packages, debug builds, or third-party hardware teardowns outside this repository.

### 2026-11-23 `JRIP1` UART boot capture diff

- `[O]` Clean systemd boot capture from `JRIP1` Pin 2 (`ttyS0`, 115200 8N1) reaches `Multi-User System`, starts `MDCIF` (listening on TCP `50800` at ~9.37 s), `Optra Edge Device UI Service`, `com.optra.DeviceUI` D-Bus proxy, `SWUpdate`, `TPM2`, `Edge Manager` / `Edge IoT` / `Edge Device Web Services`, `containerd`, `Docker`, `Azure IoT Edge daemon`, and its first `libcontainer` instance.
- `[O]` Diff against Oct 28–31 baseline captures (`docs/research/uart-boot/annotations.json`): `[  OK  ] Started Set Wifi Region Code.` appears (with `WPA supplicant` on `mlan0`), whereas the October captures started `Wifi Host AP Mgr.` instead. The four `mlock_shared_object` warnings (`libc`, `libpthread`, `libm`, `libdl`) remain unchanged.
- `[I]` `Set Wifi Region Code` vs. `Wifi Host AP Mgr.` likely reflects active Wi-Fi client (STA) mode vs. AP provisioning mode, or an intervening firmware update; correlate against the unit's current `FirmwareVersion`.

