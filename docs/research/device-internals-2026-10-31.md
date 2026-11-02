# Device internals, image lifecycle and logging map

Research note, 2026-10-31. Scope: the owner-operated Roca Sifter (Lexmark Optra
Compute 550 white-label, build target `granite2v8-sifter`; firmware strings
disagree between artifacts — see the version caveat below). This note
consolidates saved evidence only; no device contact, setting change, reboot,
deployment or credential use was performed for it. `[O]` marks an observation in
saved artifacts, `[I]` an inference.

Companion documents: [the UART/diagnostic review](diagnostic-research-2026-10-30.md),
[the surface inventory](../surfaces.md), [the encrypted log format](../log-format.md)
and the local `FINDINGS.md`.

Framing: support registration is fixed and images now reach the cloud, so upload
success is **not** the success criterion here. The goal is owner-controlled
visibility into the device — what runs, where its sockets point, where its logs
go, what its settings control and how an image moves through it. Bin-full events
in the captures are incidental observations and do not drive this research.

## Evidence actually available

Readable in this checkout:

- `device/uart/` — boot and job-watch serial captures, including
  `boot-jrip1-20261028T221520Z.log` (41,751 bytes; its companion `.json`
  records 120 s and `serial_writes: 0`),
  `job-watch-live-decoded.txt` (timestamped decode of a later boot/job) and
  `screen-before-restart-20261028.txt` (shutdown scrollback).
- `device/usb/` — later 2026-10-31 console captures:
  `uart-screen-scrollback-20261031T074747.txt` (three boots plus a long job
  window) and `uart-live-20261031T0808-job-failure.log`.
- `device/identity.json` — firmware/build identity used for the version caveat.
- `device/settings-all-20261028.json` — 121 authenticated EWS settings.
- `device/external-urls.json`, `device/external-urls-during-job.json` — device
  reachability lists.
- `device/device-logs.bin` and four `device/debug-logs-*.tgz.der` files — five
  encrypted EWS log bundles (not decryptable here).
- `device/bus-capture-20261030*.jsonl` — three MessagePack event-bus captures.
- `device/research/live-sifter-20261031/` — 1,807 initial records, 3,170
  continuation records and 11 portal snapshots.
- `device/iotedge-log-investigation/` — a prepared `GetModuleLogs` request and
  an access review; no logs were retrieved.
- `device/local-access-20261029T003706Z/results.json` — LAN probes of Docker and
  IoT Edge HTTP paths; both returned the setup SPA, not APIs.
- `device/endpoint-review-20261028T235956Z/` — endpoint review and external URL
  reachability.
- `FINDINGS.md`, `docs/surfaces.md`, `docs/log-format.md`,
  `docs/scan-exports.md`, `docs/vision-api.md`, `docs/device-findings.md`.

Not available: the host journal or `/var/log`, Docker container log files,
container filesystems, the portal tenant, plaintext EWS log bundles, the Lexmark
private decryption key, or IoT Hub management access. Statements below that
would require those are marked unresolved rather than inferred as fact.

Also present in the ignored local evidence set, but used here only where cited:
`BOARD-NOTES.md` (hardware notes), `batch-289675-scans.json` + `manifest.csv` +
`images/` (the 501-record export baseline: 501 scan JPEGs plus 10 board
photos under `images/board/`), `mitm/` (the failed proxy experiment) and
`reference/` (vendor PDFs).

Version caveat: the 2026-10-29 endpoint review recorded firmware `3.3.5`, while
the project baseline says `3.5.4`. Boot banners in the 2026-10-31 captures print
`Si Gr2-RevC1 3.3.22-6h`, a third string that may be a build/revision label
rather than the EWS firmware version `[I]`. Treat firmware-specific claims as
needing a fresh version check before replication.

## Answers at a glance

| Question | Short answer | Confidence |
| --- | --- | --- |
| Scanner processes and IPC | MDCIF owns the TCP 50800 listener; 21586 is a silent TCP service that closed all tested inputs; 21587 and 9002 carry the same MessagePack node-event stream; Unix sockets exist for LxkScanDataRemote, membroker, ScanEngine RPC and Edge Device Web Services. Unit names are observed; port-to-process ownership is mostly inferred. | Mixed |
| Image acquisition to upload | The bus exposes geometry plus a per-side handle slot, never bytes or a path. Queue entries are removed ~4 ms after ejection, so upload/indexing is outside the PageQueue tree `[I]`. No per-scan upload acknowledgement was captured. Persistence under `/var` is plausible but no spool path was observed. | Descriptor observed; byte path unresolved |
| Logging destinations | systemd journal sockets plus a “System Logging Service” at boot, LBTRACE vendor driver, pstore/ramoops crash records copied to syslog, encrypted EWS log bundle addressed to Lexmark support, a reachable remote Sematext endpoint, Docker/IoT Edge logs unread. | Destinations partly observed; contents unavailable |
| Settings consumers | Values are known from the 121-key dump (`SettingsDebugLevel=5`, `WebBrowser=true`, `WebBrowserURL=""`); readers/writers and runtime effects are not in saved source or logs. `web_url` is absent from the dump; `u8NVSMembersDataFilledIn ver 4` is absent from the EWS dump and appears as an internal MDCIF/NVS field. | Values observed; consumers unresolved |
| Supported local access | Authenticated EWS settings/log export, Vision API self-documentation, event-bus metadata subscription. No host shell, plaintext journal, container filesystem or full-resolution image route was demonstrated. | Observed limits |

## Artifact audit: service definitions, executable references, settings consumers

The saved evidence was audited for the three things the rest of this note
depends on. The boot log is rich in **unit descriptions** and **lifecycle
order**, but it contains no complete unit file, no executable path and no
process listing. That distinction drives every unresolved item below.

### What the artifacts contain

| Artifact | Contains | Does not contain |
| --- | --- | --- |
| systemd console output (`device/uart/*`, `device/usb/uart-*`) | unit descriptions, start/stop order, socket listener lines, five unit-file paths and a few quoted directives in warnings (`User=nobody`, two `ListenStream=` paths, two unknown keys), mount ordering, kernel messages | complete unit files, `ExecStart=`, scanner socket paths, PIDs |
| firmware error lines in the same output | two scanner-library source references (`_wake_scheduler,66`, `scan_queue_prune,394`) plus module tags `MDCIF` and `lbtrace` | binary paths, package names, build IDs, symbol tables |
| EWS JavaScript bundle (`device/endpoint-review-20261028T235956Z/ews-app.js`) | browser client API surface: settings keys it reads/writes, log download, diagnostics endpoints | any reference to the five target settings or the scanner services; no source map |
| settings dump (`device/settings-all-20261028.json`) | 121 key/value pairs, including `SettingsDebugLevel=5`, `WebBrowser=true`, `WebBrowserURL=""` | definitions, types beyond JSON primitives, readers, writers, defaults, ranges |
| encrypted log bundles (`device/device-logs.bin`, four `debug-logs-*.der`) | CMS EnvelopedData metadata: recipient `CN=padebug.lpdev.prtdev.lexmark.com`, serial `B7200FFE7A8AE643`, RSA key transport, AES-256-CBC | plaintext logs; no private key |
| packet captures (`device/capture-2026-10-25-2142/sifter-only.pcap`) | WAN TLS to 8883/443 and DNS from `<LAN_IP>` | any LAN-side conversation involving the device; no loopback/internal traffic (capture point is `br0`, so absence is a placement limit) |
| portal sources (`device/software-recovery-20261029T013334Z/portal-source-*`) | portal job/batch UI logic and error strings | device-side settings consumers or scanner IPC |

The five unit-file paths are the only filesystem paths for service definitions
that appear anywhere in the saved output:

```
/usr/lib/systemd/system/membroker.service:14
/usr/lib/systemd/system/powerdown-sound.service:6
/usr/lib/systemd/system/box-line-reset.service:5
/usr/lib/systemd/system/aziot-edged.mgmt.socket:7
/usr/lib/systemd/system/aziot-edged.workload.socket:7
```

They come from systemd warning text (`...:390-394`), not from a directory
listing. No file at those paths is present in the repository.

### What is missing

- No complete `.service` or `.socket` file is present; only the five
  warning-quoted fragments above.
- No process listing (`ps`, `ss -ltnp`, `/proc/<pid>/...`) is present.
- No container image list or container filesystem is present; the only
  container evidence is four overlay/netns mounts at shutdown
  (`device/uart/screen-before-restart-20261028.txt:99951-99961`).
- No socket path is recorded for LxkScanDataRemote, ScanEngine RPC or
  membroker; only their unit descriptions and listener lines. The two IoT Edge
  socket paths are the exception.
- No saved code reads or writes `SettingsDebugLevel`, `WebBrowser`,
  `WebBrowserURL`, `web_url` or `u8NVSMembersDataFilledIn`. The only
  non-document references are annotation strings for four of them in
  `docs/research/uart-boot/annotations.json` and `build_report.py`; `web_url`
  appears nowhere outside project notes.
- The EWS client reads only identity, network, wireless, hotspot and HDMI
  keys; it writes only network/hotspot keys. None of the five target keys
  appears in either set.
- No plaintext journal, syslog file, Docker log or IoT Edge module log is
  present.

### Smallest missing artifact or access per unresolved interface

| Interface | Already saved | Smallest missing artifact | Smallest missing access capability |
| --- | --- | --- | --- |
| MDCIF / TCP 50800 | listener line; accept → command → NVS sequence; cover events; reconnect behavior | MDCIF unit file (`ExecStart=`, `User=`, network-namespace directives) | read-only host shell for `systemctl cat` and `ss -ltnp` (or `/proc/net/tcp`) |
| TCP 21586 | accept/silence/close behavior; no owner | none identifiable by name; needs a port-to-process mapping | `ss -ltnp` on the host and in each container network namespace |
| TCP 21587 / 9002 | full MessagePack envelope schema and event captures | producer service definition or container image name | `ss -ltnp` plus a read-only container list (`docker ps` / `ctr containers list`) |
| ScanEngine RPC | unit description; socket listener; shutdown order | `.socket` and `.service` files with `ListenStream=` and `ExecStart=` | read-only host shell (`systemctl cat`) |
| LxkScanDataRemote | unit description; socket listener | same | same |
| membroker / Memory Tuning | unit description; socket listener; `nobody` warning; shutdown order | `.socket`/`.service` files plus any broker API header or client binary | read-only host shell; broker API documentation if it exists |
| Edge Device Web Services | unit description; listener/start lines | `.socket`/`.service` files | read-only host shell |
| Logging (journal/syslog/LBTRACE/pstore/Docker/IoT Edge) | unit names; socket listeners; mount order; LBTRACE driver load; pstore region; CMS metadata | `/etc/systemd/journald.conf`, syslog implementation/config, Docker `daemon.json`, IoT Edge module log config | read-only host shell or read-only mounts of `/var/log/journal`, `/var/log`, `/var/lib/docker/containers` |
| Settings consumers (five keys) | values; EWS client inventory; NVS boot sequence | binary or source that defines/reads each key (strings/xrefs) | filesystem access to service binaries, or a controlled setting-change experiment with before/after log capture |
| Image pipeline (acquisition→upload) | descriptors/handles/states; portal thumbnails; WAN pcap (TLS only) | spool directory path and queue metadata schema | read-only host shell plus `lsof`/`ls` during one scan, or container filesystem access |

The common dependency is a read-only host shell. Without it, the next-best
artifacts are unit files obtained through an authorized diagnostic export or a
vendor-supplied service definition. A container-only exporter cannot supply
them: it sees its own namespace, not the host’s units or the scanner’s sockets.

## 1. Process and IPC map

The boot log names systemd units and sockets but does not include complete unit
files, executable paths or `ss -ltnp` output. Port-to-process ownership is
therefore `[I]` except where a process prints its own listener line.

| Interface | Owner / unit | Binding and namespace | Transport / framing | Documented read-only operation | Evidence |
| --- | --- | --- | --- | --- | --- |
| TCP 50800 (MDCIF) | `MDC Interface` unit; binary path not captured | LAN connections refused while other ports accept, which is consistent with loopback binding, a container-network bind or a firewall rule `[I]`; exact bind address unproved | TCP; application framing unknown; HTTP unproved | None established | Boot prints `MDCIF: ... Listening for TCP connection on port 50800` (`device/uart/job-watch-live-decoded.txt:667`); later accepts a peer reported as `0.0.0.0:0`, then `Start command processing`, `primeNVSSystem`, `setting u8NVSMembersDataFilledIn ver 4` (`...:718-721`) |
| TCP 21586 | Unknown internal consumer `[I]` | LAN-reachable; accepts TCP | Silent after accept; tested inputs close it in ~5 ms; no handshake found | None | `docs/surfaces.md:73-81`; receive-only probe got zero bytes (`device/local-access-20261029T003706Z/results.json`) |
| TCP 21587 | Unknown event-bus service `[I]` | LAN-reachable; no auth | Raw TCP carrying MessagePack envelopes; sends during scan activity; an idle receive-only probe got zero bytes, so “server speaks first” is activity-dependent, not a banner | Subscribe and decode frames; no writes documented | `docs/surfaces.md:83-93`; captures under `device/bus-capture-*.jsonl` |
| TCP 9002 | Unknown event-bus service `[I]` | LAN-reachable; no auth | WebSocket; handshake succeeds on any path; binary MessagePack frames of the same envelopes | Subscribe and decode frames; no writes documented | `docs/surfaces.md:83-93`; `FINDINGS.md:717-720` |
| TCP 5000 (Vision API) | FastAPI/uvicorn process or container; owner not established | LAN-reachable; no auth | HTTP/JSON + multipart; self-documenting at `/openapi.json` | `GET /ram`; recognition routes consume images but return no image bytes | `docs/vision-api.md`; `FINDINGS.md:787-795` |
| UDP 5355 (LLMNR) | Name-resolution service `[I]` | LAN link-local | LLMNR | Name resolution only | `docs/surfaces.md:19` |
| Unix socket, LxkScanDataRemote | `LxkScanDataRemote Server Socket` + socket-activated service `[I]` | Host Unix namespace; path not captured | Unix socket; framing unknown | None established | Boot listener line (`device/uart/job-watch-live-decoded.txt:598`) |
| Unix socket, ScanEngine RPC | `ScanEngine RPC Server Socket` + `ScanEngine and RPC server` service; socket activation `[I]` | Host Unix namespace; path not captured | RPC over Unix socket; framing unknown | None established | Boot listener line (`...:600`) and shutdown ordering (`device/uart/screen-before-restart-20261028.txt:99896,99930`) |
| Unix socket, membroker | `membroker.socket` + `membroker.service` (runs as `nobody`) plus Memory Tuning Service; socket activation `[I]` | Host Unix namespace; path not captured | Broker protocol unknown; likely shared-memory/image-buffer broker `[I]` | None established | Boot listener line (`...:599`); shutdown stops Memory Broker then Memory Tuning (`screen-before-restart...:99934-99936`) |
| Unix socket, Edge Device Web Services | `Edge Device Web Services` unit | Host Unix namespace; path not captured | Unknown; likely backend for the HTTPS EWS front end `[I]` | None established | Boot listener line (`...:609`) and start line (`...:696`) |
| D-Bus system bus, filtered proxy | D-Bus proxy for containers, filtered to `com.optra.DeviceUI` only | Host D-Bus; containers see only that interface | D-Bus method calls/signals; introspection not captured | Unknown without interface introspection | Boot start line (`...:652`) |
| `/run/iotedge/mgmt.sock`, `/run/iotedge/workload.sock` | Azure IoT Edge daemon (`aziot-edged`) | Host Unix namespace; normalized from `/var/run/iotedge/*` at boot | IoT Edge management/workload API over Unix sockets | Presence does not prove caller authorization or reachability from a skill container | Boot normalization lines (`...:391-392`) |
| Docker API socket | Docker daemon / containerd | Host Unix namespace; boot confirms a “Docker Socket for the API” listener (`...:608`) but not its path (conventionally `/run/docker.sock`) `[I]` | Docker HTTP API over Unix socket | None established | Not owner-reachable over LAN: `/containers/json?all=1` returned the setup SPA HTML (643 bytes), not JSON (`device/local-access-20261029T003706Z/results.json`) |

The names suggest roles — `LxkScanDataRemote` for scan-data transport,
`ScanEngine RPC` for engine control, `membroker` for shared buffers — but no
client, message schema or handle mapping was captured. Treat those role
assignments as hypotheses, not documented interfaces.

Interpretation boundaries:

- A listening TCP port is not evidence of HTTP. MDCIF prints a TCP listener;
  no request format or HTTP response has been observed (`docs/surfaces.md:65-71`).
- Adjacent port numbers do not imply a shared protocol. 21586 is silent and
  closed all tested inputs; 21587 carries MessagePack events.
- The MDCIF peer fields `0.0.0.0:0` are not proof that the client is localhost;
  they are consistent with an internal peer but do not establish its namespace.
- The event bus carries node metadata only. It does not carry image bytes,
  paths, byte counts or upload acknowledgements (`docs/surfaces.md:140-154`).

## 2. Settings consumers

Values below are from the authenticated dump unless stated otherwise. The dump
records JSON primitives (number, boolean, string), which are observed; semantic
types, definitions and consumers are inferred and marked accordingly.

| Key / field | Value in dump | Type / definition status | Reader / writer status | Runtime effect and destination |
| --- | --- | --- | --- | --- |
| `SettingsDebugLevel` | `5` (`device/settings-all-20261028.json`) | JSON number (integer); semantic type and definition not in repo `[I]` | The settings API can write settings (demonstrated with `SettingsPort8080`; `FINDINGS.md:77-85`), but no write of this key was performed; reader process not identified. The owner separately reported level 7 during scanning (owner report, not a saved artifact), but no known-level baseline was captured. No level was changed for this analysis. | Unproved. Vendor LBTRACE infrastructure exists (`Initialize lbtrace settings`, boot lines 622/655), but no saved evidence connects this key to LBTRACE verbosity, journald, syslog or a file path. Do not claim that raising it produces more logs until a controlled before/after capture shows it. |
| `WebBrowser` | `true` | JSON boolean; semantic definition not in repo `[I]` | Reader/writer unknown. An “Optra Edge Device UI Service” starts at boot (`...:649`) and a D-Bus proxy is filtered to `com.optra.DeviceUI` (`...:652`), but neither is proven to consume this key. | Unproved. It may gate an embedded browser/UI component rather than navigation. No navigation, fetch or proxy behavior was observed, and no log destination was identified. |
| `WebBrowserURL` | empty string (`""`) | JSON string; semantic definition not in repo `[I]` | Consumer process unknown. No code or log shows a fetch, navigation or proxy request using this value. | Unproved. An empty value is consistent with “no URL configured”, not with “feature disabled”. A localhost destination would not by itself change the origin or namespace of a request made by another process or container. No log destination was identified. |
| earlier `web_url` hypothesis | absent from the dump (lookup returns no key) | Not a confirmed setting key in this firmware’s dump | No reader/writer identified. It appears only as an earlier hypothesis in project notes. | Do not conflate it with `WebBrowserURL`. There is no saved evidence that a key named `web_url` exists on this unit. |
| `u8NVSMembersDataFilledIn ver 4` | absent from the EWS dump (internal field) | Internal MDCIF/NVS field; name suggests an unsigned 8-bit member plus version marker `[I]`, but type and semantics are unproved | Written by MDCIF after a peer connects and command processing begins: boot shows accept → `Start command processing` → `primeNVSSystem` → `setting u8NVSMembersDataFilledIn ver 4`. It is not established as a writable EWS setting, debug level or firmware version. | Internal initialization marker for NVS members after MDC connection `[I]`. Its effect on scanning or persistence is unknown. Connection-to-marker delays in seven saved boots span ~114–120 ms on each boot’s own MDC clock (`diagnostic-research-2026-10-30.md:60`; `device/usb/uart-screen-scrollback-20261031T074747.txt:99994`); that is temporal order, not a call stack or proof of which command triggered it. |
| `SettingsPort8080` (context) | `false` at dump time; later set true via authenticated PUT and verified in settings, but port 8080 stayed closed and port 5000 remained open (`FINDINGS.md:77-85,147-148`) | Hidden boolean toggle by name `[I]`; definition not in repo | Writer is the settings API; reader/gate unknown. A reboot test was pending and is not recorded as completed here. | Unproved as a gate for port 5000 or any other service. Do not use it as a diagnostic control without a documented effect and rollback plan. |

Namespace caution for URL settings: host loopback (`127.0.0.1` on the device),
a browser process’s loopback, and a container’s loopback are different network
namespaces unless explicitly shared. A URL that works from one is not evidence
that another process can reach it.

## 3. Image lifecycle

### Acquisition and descriptor

The event bus reports per-side state and an image descriptor:

```
PageQueue/<id>/Front|Back/state   Scanning -> Safe -> Ejected
PageQueue/<id>/Front|Back/Image   composition, handle, mediaWindow,
                                  outputCanvas, compression
PageQueue/<id>/foil               Detected | NotDetected
PageQueue/<id>/eject              added with the page
PageQueue/<id>                    removed after ejection
```

Observed descriptor values across captures:

- media window: 1800 × 2020 at 600 dpi, composition `Rgb24`;
- output canvas: 870 × 1170 at 300 dpi, compression `Jpeg`;
- front handle `0`, back handle `1`;
- front output-canvas x = -420, back x = -450 (side-specific crop offset);
- no path, URL, byte count or payload anywhere in the stream.

The handle is **not** a durable image id. In one live capture the analyzer found
129 distinct pages using handle 0 and 129 using handle 1; in the continuation,
226 each. Handles are per-side slot indices reused for every page
(`tools/analyze-bus.py`, run over the saved captures). Therefore a handle cannot
be used as a key to locate bytes on disk or in a store after the fact.

### Buffer owner and byte access

The most plausible buffer owner is the Memory Broker (`membroker`) plus Memory
Tuning Service. `membroker.socket` is listening before MDCIF starts, and both
memory services stop around MDCIF during shutdown
(`device/uart/job-watch-live-decoded.txt:599,657`;
`device/uart/screen-before-restart-20261028.txt:99933-99937`). A broker named
“membroker” with a socket unit is consistent with shared-memory image buffers,
but no API, segment name or handle-to-buffer mapping was captured. This remains
an inference.

Byte-access paths actually observed:

- Vision API port 5000 **accepts** an image on `/sifter/recognize_card`
  (multipart) and returns catalog identification, score and timing fields; it
  never returns image bytes (`docs/surfaces.md:48-63`, `FINDINGS.md:787-795`).
- Event bus ports 9002/21587 return descriptors only.
- EWS has no tested image/file retrieval route (`docs/surfaces.md:45-46`,
  conclusion at lines 180-191).
- Portal thumbnails are reachable with a seller session at 446 × 600 JPEG;
  ten larger-variant guesses returned 404 (`docs/surfaces.md:161-173`,
  `docs/scan-exports.md:12-15`).

No owner-reachable surface returned full-resolution scan bytes.

### Persistence

Saved boot evidence shows:

- root is read-only SquashFS on dm-verity over `/dev/mmcblk1p3`
  (`device/uart/job-watch-live-decoded.txt:125,376`);
- eMMC has eight partitions (`...:350-354`);
- `/var` is mounted from the persistent label `data`
  (`...:513,561-562`);
- `/var/volatile` is mounted separately (`...:563,567`);
- Docker’s data path is under the eMMC-backed `/var`: shutdown unmounts
  `/var/lib/docker` before `/var`
  (`device/uart/screen-before-restart-20261028.txt:100011-100030`) `[O]`; a
  docker-seed partition is expanded at boot (`...:565,570`);
- a “Flush Journal to Persistent Storage” unit runs at boot (`...:566,571`);
  whether journald actually stores records under `/var/log/journal` is not
  captured;
- startup includes a conditional “Do box line reset if /var/blurb exists”
  (`...:618,638`) — this is not a documented factory-reset procedure.

No scan spool directory, queue metadata file or image-store path appears in the
saved logs. The startup message about pruning page 0 from a scan queue shows a
queue exists at boot but does not identify its backing store or prove file
deletion (`diagnostic-research-2026-10-30.md:68`).

### Upload and acknowledgement

The device’s reachability list includes portal, IoT Hub/DPS endpoints,
`bucket.optra.com`, container registry and
`logsene-journald-receiver.sematext.com`
(`device/endpoint-review-20261028T235956Z/external-urls.json`;
`FINDINGS.md` §6). The event bus contains no upload event, byte count or server
acknowledgement. Portal thumbnails for the documented batch prove that at least
some images reached cloud storage/indexing, but they do not prove per-scan
upload success or retention of full-resolution originals.

Timing observed by the analyzer:

| Transition | n (initial capture) | median |
| --- | ---: | ---: |
| Scanning → Safe per side | 258 | ~0.83 s |
| Safe → Image descriptor per side | 258 | ~0.06 s |
| Image → Ejected per side | 257 | ~1.36 s |
| Ejected → node removed per side | 258 | ~0.004 s |
| Scanning → node removed per side | 256 | ~2.26 s |

The ~4 ms ejection-to-removal median means the PageQueue entry disappears almost
immediately after ejection. Any upload or indexing step would therefore have to
be tracked outside the PageQueue tree (or inferred from portal state), not from
bus node lifetime `[I]`.

### Four states and how to distinguish them

| State | What saved evidence would look like | Concrete diagnostic path |
| --- | --- | --- |
| RAM-only / buffer released without durable copy | Descriptor + handle observed; node removed quickly; no file path in any log; no portal item for that side after a reasonable wait. Cannot be proven from network surfaces alone because handles are reused slots and node removal does not prove buffer free. | Capture bus with UTC timestamps for one controlled scan; record page id/side/handle and ejection time; compare side counters to portal item count for that batch after upload window. If sides are missing from portal and no host file exists under authorized inspection, RAM-only/released is the leading explanation — still an inference without host instrumentation of membroker/MDCIF. |
| Disk-persisted (spool or cache) but not uploaded/indexed | A recent JPEG matching output-canvas geometry exists under `/var`, a Docker volume or another persistent mount with mtime near scan time; portal item absent or thumbnail missing. No such path has been observed yet. | With authorized read-only host access, list candidate paths (`/var`, `/var/lib/docker`, mounted volumes) for files modified during the scan window; hash and inspect geometry; correlate mtime to page id/ejection time from the bus capture. Do not assume a named volume exposes these paths to a skill container — it exposes only what is mounted to that module (`diagnostic-research-2026-10-30.md:78`). |
| Uploaded but unindexed / portal missing item or thumbnail | Device reached Ejected with an Image descriptor; portal batch item count is short of side-counter delta, or item exists but thumbnail returns non-200/404 while other items work. Object-storage keys are not listable anonymously (`bucket.optra.com` returns 403). | Compare per-session side-counter delta (`Status/SideCountPermanent/adfFront/adfBack`) with portal matched + unidentified item counts for that batch; fetch each item’s thumbnail with normal seller auth and record status/size/hash; check whether missing items cluster by time window or side (front/back). This distinguishes indexing/CDN gaps from acquisition gaps without touching device settings. |
| Deleted after upload or retention expiry | Portal item may exist while local file is gone; or both absent after retention/prune interval. Node removal alone cannot prove deletion of persisted files (`diagnostic-research-2026-10-30.md:66`). No retention policy was captured locally. | Deletion timing would need host filesystem/journal evidence or vendor documentation; no local surface exposes a retention setting. |

Important limits:

- A descriptor is metadata, not proof of a successful byte read.
- Node removal is queue removal only; it does not prove buffer free or upload success.
- Handle reuse proves slot reuse, not deletion.
- Portal thumbnail presence proves cloud-side availability of a thumbnail, not full-resolution retention.
- No saved boot message establishes which of the four states applies to a given
  scan side.

## 4. Logging destinations

### systemd journal

Observed at boot:

```
systemd[1]: Listening on Syslog Socket.
systemd[1]: Listening on Journal Socket (/dev/log).
systemd[1]: Listening on Journal Socket.
systemd[1]: Starting Journal Service...
systemd[1]: Started Journal Service.
...
Starting Flush Journal to Persistent Storage...
Finished Flush Journal to Persistent Storage.
```

(`device/uart/job-watch-live-decoded.txt:416-423,450,484-486,566,571`;
also visible in the earlier boot capture.)

Interpretation:

- Host unit stdout/stderr goes to journald by default under systemd `[I]`.
- Kernel messages are read by journald from `/dev/kmsg` in addition to appearing
  on UART `[I]`.
- Volatile journal would be under `/run/log/journal` (tmpfs); persistent journal,
  if enabled by journald configuration, would be under `/var/log/journal`.
  The boot message “Flush Journal to Persistent Storage” plus the persistent
  `/var` mount makes `/var/log/journal` plausible but does **not** prove the
  directory exists or that journald is configured to keep records there rather
  than in volatile storage.
- Exact journald configuration (`Storage=`, retention, rate limits), file paths,
  permissions and group membership were not captured.
- Typical access requires root or membership in `systemd-journal`, plus read
  access to the journal files.

### syslog

The boot listens on a “Syslog Socket” and starts a “System Logging Service”
(`...:416-417,627`); whether the latter is rsyslog, syslog-ng or another
implementation is not captured. Its configuration, destination files and remote
forwarding are also not captured. A conventional file such as
`/var/log/messages` is possible but unproved.

### LBTRACE

Boot includes `lbtrace: module license 'Proprietary' taints kernel`,
`Starting the LBTRACE driver` (`...:485`) and “Initialize lbtrace settings”
(`...:622`, finished at `...:655`). LBTRACE appears to be a vendor kernel
driver/trace facility whose settings are initialized at boot. No device node,
procfs path, ioctl interface or log destination was captured.
`SettingsDebugLevel=5` may influence it by name association only; there is no
evidence connecting the two.

### pstore / ramoops

Observed:

```
pstore: Registered ramoops as persistent store backend
ramoops: using 0x100000@0x50000000, ecc: 0
...
Starting Log pstore crash archives to syslog...
Finished Log pstore crash archives to syslog.
```

(`...:196-198,628,641`.)

Ramoops reserves 1 MiB of crash-record RAM at `0x50000000`. At boot a service
copies pstore crash archives into syslog (and therefore possibly journald,
depending on the syslog path). This is useful for kernel
panic/oops records across reboot, **not** for live scanner logs and **not** an
image store or power-loss persistence guarantee.

### EWS encrypted log bundle

Authenticated `GET /webservices/logs` returns a PKCS#7/CMS EnvelopedData bundle:
RSA key transport to a Lexmark support certificate (3072-bit RSA), AES-256-CBC
content encryption with a fresh IV per bundle, ciphertext in contiguous
4096-byte blocks from about offset 686 to EOF (`docs/log-format.md:28-31,43-46`). The filename pattern implies an inner `.tgz`. Five samples were
parsed structurally.

This bundle is sealed to the vendor support recipient
(`CN=padebug.lpdev.prtdev.lexmark.com`, serial recorded in the doc). Without the
private key it cannot be decrypted locally through any demonstrated route.
It is an export mechanism to Lexmark support, not an owner-readable local log.

### Remote application-log upload

The device can reach
`https://logsene-journald-receiver.sematext.com:443`
(`device/endpoint-review-20261028T235956Z/external-urls.json`); the endpoint name and project
notes associate it with application-log upload / remote diagnostics `[I]`.
The client configuration (which journal fields are sent, credentials,
retention) was not captured locally and is not owner-readable through any tested
surface.

### Docker and IoT Edge logs

Docker starts at boot (`...:703`, “Docker Application Container Engine”), but
the logging driver was not captured. If the default json-file driver is used,
container logs would conventionally live under
`/var/lib/docker/containers/<id>/<id>-json.log` on the host filesystem;
if journald is used they would go to the journal instead. Neither path was read.

IoT Edge module logs are normally retrieved through the `GetModuleLogs` direct
method on `$edgeAgent`. A request file was prepared targeting all modules with
`since: 1h`, `tail: 100`
(`device/iotedge-log-investigation/get-module-logs-request.json`) but execution
status is “Prepared only; no IoT Hub management access established; no module
logs retrieved” (`.../access-review.json`). Presence of management/workload
sockets does not by itself prove API reachability or caller authorization.

### Portal log view

The Optra portal is reported to expose a device log view (DEVICES → device →
CONFIGURE DEVICE → VIEW LOGS) for owners with tenant access `[I]`. That is a
cloud-side route requiring tenant privilege; it was not available for this unit
and no local artifact captures the route.

### UART console

JRIP1 output was captured at 115200 8N1 with a read-only `cat` pipeline
(`tools/serial-capture.sh`); the capture tool issues no serial writes.
It shows boot/service messages but no getty/login prompt was established.
UART output is not an interactive shell.

## What an exporter would need

A container-only exporter sees its own namespace, not the host’s. Each log
source therefore needs an explicit grant:

Named-volume privileges alone do not expose another container’s files, the host
journal or Docker logs (`skills/sifter-export/PRIVILEGES.md`;
`diagnostic-research-2026-10-30.md:78`). A diagnostic exporter would need one or
more explicit read-only sources:

| Source to export | Minimum access needed |
| --- | --- |
| systemd journal (persistent) | Read-only mount of `/var/log/journal`, plus read permission (root or `systemd-journal`) |
| systemd journal (volatile) | Read-only mount of `/run/log/journal`, same permission caveat |
| syslog files / remote config | Read-only mount of `/var/log`, plus knowledge of which implementation/config is active |
| pstore crash records | Read-only mount of `/sys/fs/pstore`, usually root-only |
| Docker container logs (json-file driver) | Read-only mount of `/var/lib/docker/containers`, plus permission to read root-owned files |
| Docker logs via API | Mounting the Docker socket grants broad daemon control — higher risk than read-only file mounts |
| LBTRACE buffer/trace | No device node or procfs entry was observed; would need vendor documentation for the interface and ioctl protocol |
| EWS encrypted bundle decryption | Lexmark private key or vendor decryption service — unavailable locally |

Export mechanisms would be file copy/tar for journal, syslog, pstore and Docker
json-file paths; `journalctl --output=export` for journald; Docker API
`/containers/{id}/logs` (socket access); IoT Edge `GetModuleLogs` (Hub
management access); EWS `GET /webservices/logs` (owner Basic auth, vendor-sealed
result); portal VIEW LOGS (tenant access); and a read-only UART capture (no
login).

A minimal safe prototype would mount only explicit read-only paths, run as root
or with journal group access inside its own container namespace, write a tar +
manifest (source path list, sizes, mtimes, SHA-256) to an owner-controlled USB or
HTTPS endpoint, and make no device changes beyond its own deployment.

Retention policy is not captured for any source: journald
`Storage=`/`SystemMaxUse=`, syslog rotation, Docker json-file rotation and EWS
bundle lifetime are unrecorded; pstore has a 1 MiB region but its overwrite
behavior is also unrecorded. A one-shot export therefore proves only what
existed at export time, not that the same records survive a later failure.

## Supported local diagnostic access

What exists today:

Authenticated EWS settings export (121 keys, `/webservices/settings/`),
encrypted log download (`/webservices/logs`), diagnostics screenshot endpoint
`/webservices/diagnostics/screenshot` (HTTP 500; the saved notes say “no display
attached”, but no response body or server-side reason was captured),
external URL reachability list (`/webservices/diagnostics/external/urls`) and
proxy configuration/test endpoints (`/webservices/proxy`,
`/webservices/proxy/test`).
Vision API self-documentation at `/openapi.json`, four routes only.
Event bus subscription on 9002/21587 (metadata only).
No tested local endpoint returned plaintext logs or scan-image bytes.

What does **not** exist as demonstrated owner access:

SSH/Telnet/Docker/IoT Edge management ports from LAN:
22/2375/2376/15580/15581 refused (`access-review.json`);
50800 refused from LAN while other ports accept;
8080 closed even after setting toggle;
21586 silent/no handshake.
Local HTTP probes of `/modules?api-version=2018-06-28` and
`/containers/json?all=1` returned setup SPA HTML (643 bytes), i.e.,
fall-through routing rather than APIs.
No host shell was obtained. Authorized host access (root shell or a vendor
service session) would settle binding and journal questions but was not
available for this analysis.

Other routes remain unproven:

No supported local installer or proven owner enrollment/deployment route was
established for this OEM unit.

Lens links were an owner-supplied lead for deployed skill WebUIs;
no verified link-generation/auth flow for this OEM unit was obtained,
and WebUI access would not itself grant installation or host-log access.
USB container import/firmware installation has no matching OEM/build evidence;
a Docker tar is inert without an authorized loader/daemon.
Factory reset has no verified behavior that enables SSH,
console/local install or an owner tenant;
the conditional box-line-reset unit is not documented as factory reset.
USB keyboard interruption at U-Boot was never observed;
Linux EHCI/HID initialization occurs after U-Boot,
so Linux USB keyboard support does not prove U-Boot keyboard input.

The concrete vendor grant that would unblock diagnostics:
an authorized diagnostic deployment or log export with explicit target sources,
mounts/permissions and an owner-access destination.

## Three highest-value next experiments

### A — Correlate one scan’s page ids with portal items

Hypothesis:
the portal item count may not equal the number of ejected sides even when cloud
upload succeeds; the goal is to locate where a side goes after ejection, not to
diagnose an upload failure.

Prerequisites:
owner portal access (or exported batch JSON + manifest);
a bus capture that records UTC per record (the three older
`device/bus-capture-20261030*.jsonl` captures lack it; the live-sifter captures
have it, and `tools/bus-probe.py` now writes one per record);
one controlled scan of known cards;
note start/end UTC and side counters before/after.

Exact observation:
for each page id/side record Scanning/Safe/Image/Ejected times and handle;
compute delta of Status/SideCountPermanent/adfFront+adfBack;
compare with matched + unidentified item count for that batch;
list missing sides and whether they had Image descriptors/Ejected states;
fetch each present item’s thumbnail status/size/hash.
The offline helper `tools/correlate-portal.py` already joins saved bus segments
to portal counter snapshots and prints matched/page ratios; it is descriptive
only and cannot prove a specific page was uploaded.

Distinguishing outcomes:
all sides Ejected with Image but portal count short ⇒ post-ejection upload/index gap or a portal-side count difference;
missing sides lack Image or never reach Ejected ⇒ acquisition/processing failure;
portal count matches but thumbnails fail ⇒ storage/CDN/index issue;
no missing sides ⇒ this batch does not reproduce a count mismatch.

Disruption risk:
low — read-only bus subscription plus portal GETs;
respect rate limiter (~120 requests can trigger >20 min device-global ban;
space requests).

### B — Authorized read-only journal export around one scan

Hypothesis:
journald contains scanner/MDCIF/ScanEngine/Docker/IoT Edge records that are not
visible on the console,
and an explicit read-only mount of `/var/log/journal`
is sufficient to retrieve them without host shell.

Prerequisites:
vendor/portal authorization to deploy a diagnostic skill;
explicit read-only volume mount(s) for `/var/log/journal` and/or
`/run/log/journal` (optionally `/var/log`, `/sys/fs/pstore`);
ARM64 image;
owner-controlled destination (USB or HTTPS);
rollback plan because deployment changes device state.

Exact observation:
exporter lists journal file paths/sizes/mtimes/SHA256;
extracts entries for units around the scan timestamp:
MDCIF/MDC Interface,
ScanEngine/RPC,
LxkScanDataRemote,
membroker/Memory Tuning,
Docker/Azure IoT Edge;
record whether entries exist and include error text;
compare timestamps to bus page ids/ejection times.

Distinguishing outcomes:
journal files exist and contain unit records ⇒ logging path viable,
the pipeline has host-side evidence;
mount empty/permission denied ⇒ named-volume privilege insufficient,
journal volatile/different path;
only Docker logs contain errors ⇒ need container log mount/driver change,
higher privilege;
no relevant entries ⇒ logging level/destination does not cover scanner path,
next step is a baseline capture before any `SettingsDebugLevel`/LBTRACE change
(that change is out of scope for this task and needs its own authorization and
rollback plan).

Disruption risk:
medium — installation/deployment may interrupt jobs;
read-only mount itself low risk,
but deployment requires authorization and rollback plan.

### C — Passive inspection of MDCIF binding and peer

Hypothesis:
MDCIF port 50800 is bound to loopback, a container network namespace or a
firewalled interface,
not exposed as an owner-facing service,
and its peer is an internal scanner controller/client rather than LAN software.

Prerequisites:
authorized host access or container network namespace inspection;
or vendor-documented MDCIF client spec.
Without host access this cannot be settled from LAN alone.

Exact observation:
bind address from `ss -ltnp` / `/proc/net/tcp`;
owning PID/cgroup/socket inode;
peer connections during scan from `ss -tnp`;
whether any documented client library/spec exists.
Do not send guessed payloads during scans.

Distinguishing outcomes:
127.0.0.1 bind ⇒ LAN refusal expected,
owner access requires host/container namespace,
not firewall change;
container IP bind ⇒ reachable only from container network,
need sidecar/policy;
0.0.0.0 bind plus firewall refusal ⇒ filtering issue,
still no protocol proof;
documented client spec found ⇒ choose supported read-only op instead of probing.

Disruption risk:
low if passive inspection only;
medium if requiring host shell/deployment.

## Reproducing this analysis

All commands are offline; the analyzers read only saved files, and the syntax
check writes only Python bytecode cache:

```sh
python3 tools/analyze-bus.py device/research/live-sifter-20261031/sifter-live-20261031T0551.jsonl
python3 tools/analyze-bus.py device/research/live-sifter-20261031/events-continuation.jsonl
python3 tools/correlate-portal.py \
  device/research/live-sifter-20261031/sifter-live-20261031T0551.jsonl \
  device/research/live-sifter-20261031/events-continuation.jsonl \
  --portal device/research/live-sifter-20261031/sifter-portal-20261031.jsonl
python3 -m py_compile tools/bus-probe.py tools/analyze-bus.py tools/correlate-portal.py
```

`tools/bus-probe.py` is the only tool that contacts the device; it is not run
above. It subscribes read-only to 21587/9002 and now records a UTC timestamp per
message so future captures can be joined to portal snapshots.

## Unresolved items

No saved artifact establishes:

process-to-port ownership for MDCIF, 21586, 21587 and 9002 beyond unit names;
MDCIF framing/protocol or HTTP support;
handle-to-buffer mapping or image byte retrieval from any owner surface;
scan spool/persistence path or retention policy;
per-scan upload acknowledgement;
plaintext local logs or host journal contents;
settings consumer source code for SettingsDebugLevel, WebBrowser, WebBrowserURL, web_url and u8NVSMembersDataFilledIn;
supported installer/factory-reset/USB-keyboard route;
full-resolution image retention location.

These are access gaps first artifacts second:
the missing artifacts are unit files/source code, host filesystem listings, journal contents and vendor protocol specs — not more endpoint guesses.
