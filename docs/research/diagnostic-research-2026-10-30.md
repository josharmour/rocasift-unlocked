# Internal diagnostics, settings and UART research

Consolidated October 30, 2026 (America/Los_Angeles; captures/report also use October 31 UTC). This note records the investigation's results and unresolved prerequisites. `[O]` means observed in saved evidence, `[I]` means an inference, and **unverified** means no supporting implementation or successful test was established. It supersedes stronger claims in earlier notes where identified below.

## Complete UART analysis

Open the [self-contained annotated report](uart-boot/roca-uart-annotated.html) locally in a browser, or download the [complete ZIP](uart-boot/roca-uart-report.zip). GitHub's source viewer does not execute the report's search controls.

Every entry includes its original source line, meaning, relevance to scan failures/missing images/settings/log access, next verification, and confidence. Machine IDs, runtime identifiers and credential-like values are redacted in quoted text and generated explanations. Original captures remain under ignored `device/uart/`.

| Coverage | Count |
| --- | ---: |
| UART/text files inventoried, including 13 empty files | 24 |
| Original physical LF-delimited lines mapped | 103,380 |
| Distinct exact source-line byte hashes | 2,605 |
| Original-source display entries | 3,650 |
| Additional lines represented by eight identical adjacent repeat ranges | 99,730 |
| Reconstructed message lines from 978 timestamped byte records | 732 |
| Total display entries, including reconstructed views | 4,382 |

The 103,380 lines are **not** 103,380 distinct meaningful messages: 99,823 source lines are classified as formatting/nonsemantic capture content. The scrollback alone contains 100,055 physical lines and 339 nonblank lines. The existing decoded file and reconstructed view overlap the raw byte capture; they are not independent boots.

The baseline `boot-full-jrip1-pin2.log` contains 708 lines and ends while Docker starts. `boot-jrip1-20261028T221520Z.log` has 725 lines and continues through a container and MDC initialization. The timestamped byte source reconstructs to 732 lines, reaching cover events omitted from its earlier 720-line decoded derivative. A 183-line capture contains partial startup. Keep those boots separate.

[O] The validator checks each source line's SHA-256 against its annotation mapping, unchanged source-file hashes, redaction across all text fields and reassembled hexadecimal records, HTML links/IDs, and archive integrity. JavaScript syntax was also checked. Visual browser review was not completed: browser policy rejected local `file:` navigation; no workaround was attempted.

Rebuild locally with the private original captures present:

```sh
python3 docs/research/uart-boot/build_report.py
python3 docs/research/uart-boot/validate_report.py
```

Set `ROCA_UART_SOURCE` to another authorized capture directory when needed. `coverage.json` inventories sources; `line-map.jsonl` maps every physical line to an entry in `annotations.json`. The generated report records the original analysis date in UTC.

## Confirmed architecture and useful log destinations

- [O] U-Boot 2022.01, Linux 6.12.54-yocto-standard, ARM64, systemd 255 and Lexmark Poky/Yocto 5.0.7 scarthgap appear in the boot output. Machine-model strings include `mv6270 Cobalt Edge yyz00b`; those strings are not independent silicon identification.
- [O] Kernel arguments route console output to `ttyS0,115200n8`. Linux also registers `ttyS1` and `/dev/ttyLPP0`. No physical pinout, usable receive path, getty or interactive login follows from those registrations.
- [O] Root is read-only SquashFS on a dm-verity mapping over `mmcblk1p3`. SHA verification and dm-verity establish integrity operations, **not encryption or a complete security-fuse policy**. AVS efuse fields concern voltage calibration.
- [O] The eMMC reports 14.5 GiB and eight logical partitions. `/var`, volatile mounts, Docker storage and actual overlay2 merged mounts appear in startup/shutdown. None identifies a scan spool or proves image persistence.
- [O] Ramoops reserves 1 MiB; journald, syslog, persistent-journal flushing and pstore archival/logging services start. These are concrete diagnostic leads, but paths, retained contents and application coverage require configuration/export evidence. Ramoops is crash-record RAM, not an image store or a power-loss persistence guarantee.
- [O] `LxkScanDataRemote`, `ScanEngine RPC` and `membroker` sockets exist. Their unit definitions and client code are needed to identify transport, permissions, framing and supported read-only operations. Their names do not establish a mapping to port 21586.
- [O] IoT Edge management/workload Unix paths are normalized to `/run/iotedge/mgmt.sock` and `/run/iotedge/workload.sock`. Docker API and Azure identity/certificate/key/TPM services also appear. Local identity plumbing does not confer operator-tenant management privileges.

## Service and settings map

| Interface / setting | Evidence | What remains unresolved |
| --- | --- | --- |
| 5000 | Historical API schema/experiments identify the Vision recognition API; see [Vision API](../vision-api.md). | An image-consuming recognition endpoint is not a scan-image retrieval endpoint. |
| 9002 / 21587 | Historical captures contain WebSocket/raw-TCP MessagePack node events. | Metadata does not prove image durability or successful cloud upload. |
| 21586 | Historical tests recorded silent accepted TCP connections and closure after tested inputs. | Authentication, owner process, framing and valid handshake remain unknown. “Any input” overstates a finite test set; do not repeat guessed payload testing during scans. |
| 50800 / MDCIF | UART explicitly prints a TCP listener. LAN connection attempts were refused in prior observations. | HTTP is unproved. Refusal does not distinguish loopback/container binding, service lifetime or filtering. Peer fields `0.0.0.0:0` are not proof of a localhost client. |
| `SettingsDebugLevel` | The owner reported level 7 during scanning; host logging and vendor LBTRACE infrastructure exist. | No comparable known-level baseline proves a verbosity change, consumer or destination. No level was changed for this analysis. |
| `WebBrowser`, `WebBrowserURL` / earlier `web_url` hypothesis | A device UI service and a D-Bus proxy filtered to `com.optra.DeviceUI` appear. | The exact setting consumer, fetch/navigation behavior, process and network namespace remain unverified. A localhost destination does not automatically change the origin of a request. No localhost/proxy test was performed. |
| `u8NVSMembersDataFilledIn ver 4` | Follows MDC connection, command-processing and `primeNVSSystem` messages in saved boots. | Internal field/type/version semantics require source. It is not established as a writable EWS setting, debug level or firmware version. |

[O] In three saved sequences, connection-to-data-filled-marker delays are approximately 116 ms, 119 ms and 115 ms on each sequence's own MDC clock. This is temporal order, not a captured call stack or proof which command triggered initialization. The owner's separate `00133.072456` marker was not found in the saved files; its neighboring context is unknown.

## Live event evidence and failure interpretation

[O] The additional local evidence retained under `device/research/live-sifter-20261031/` comprises 1,807 initial event records, 3,170 continuation records and 11 portal snapshots. These contain receipt timestamps and node/status observations; raw job identifiers and captures are not published. Earlier published captures and schema are described in [surfaces.md](../surfaces.md).

[O] The bus reports per-side `Scanning`, `Safe`, `Ejected`, foil state, counters and image descriptors. Descriptor geometry is not a successful byte read, durable file or server acknowledgement. Node removal does not establish deletion of persisted files.

[I] Startup `scan_queue_prune` messages for page 0, scheduler-before-init errors, PWM fallback, TPM self-test and library-memory-locking warnings need correlation with an actual failing scan. Their presence in boot logs alone does not diagnose lost cards. The scrollback also contains orderly shutdown; its socket closures must not be presented as spontaneous crashes.

To locate a failure, correlate one scan/page identifier across acquisition, processing, buffer/spool assignment (if any), upload attempts/retries and server acknowledgement. Distinguish RAM-only data, disk-persisted data, uploaded-but-unindexed data and deleted data. No saved boot message establishes which case applies. A stalled portal state and healthy sampled host telemetry do not by themselves prove a cloud-orchestrator defect.

## Diagnostic skill and access feasibility

The existing [exporter](../../skills/sifter-export/README.md) is a draft, not a demonstrated owner-installable log reader.

| Question | Result / prerequisite |
| --- | --- |
| Can a container package be prepared locally? | A Docker/Compose prototype exists. Building it does not establish install permission or device access; no build/deployment was performed in this consolidation. |
| Can the owner install it with present physical/EWS-only access? | No supported local installer or proven owner enrollment/deployment route was established. |
| Are named volumes/removable-media privileges enough? | Only for data actually mounted or delivered to that module. A private named volume does not expose another container's files, host journal or Docker logs. |
| Can a module call `GetModuleLogs` on edgeAgent? | Presence of a management/workload socket alone proves neither API reachability nor caller authorization. A supported grant, documented invocation route and target-runtime compatibility are required. |
| Can device identity or a serial number replace operator access? | Device-scoped identity and cloud service management are different authorization domains. No self-service tenant-management grant was demonstrated. A generic guide's serial-based initial EWS password is not a universal portal credential. |
| What vendor grant would make it concrete? | An authorized diagnostic deployment or log export, with explicit target log sources/mounts/API permissions and a supported owner-accessible destination. |

`lens.optra.io` was an owner-supplied lead for deployed skill WebUIs. An existing legitimate link might expose an already-installed UI, but no verified link-generation/authentication flow for this OEM unit was obtained. WebUI access does not itself grant installation or host-log access. No URL/serial enumeration, credential replay or tenant probing was performed for this analysis.

## USB, reset and boot-input questions

- **USB installation:** No supported OEM 8085-001/firmware 3.5.4 USB container-import mechanism was established. A Docker image tar or Compose file is inert without an authorized loader/daemon. Generic IoT Edge offline operation can continue a previously provisioned deployment; it is not proof of USB deployment support. Docker technically can run independently of IoT Edge when authorized host/daemon access exists, while this device's supported skill lifecycle may impose additional management requirements.
- **Factory reset:** No verified reset behavior establishes that it enables SSH, a console, local installation or an owner tenant. The conditional `box-line-reset` unit is not a documented factory-reset procedure. Determine enrollment persistence, erased state and reactivation prerequisites before deciding whether the future debugging benefit justifies it.
- **USB keyboard at boot:** Linux EHCI/HID initialization occurs after U-Boot. No observed U-Boot keyboard initialization, stdin configuration or countdown proves keyboard interruption is available. Stopping boot would also not by itself establish a Linux shell or change verification policy. No reboot/input experiment was performed for this analysis.

## How related published research helps

Earlier local notes cite NCC Group's Lexmark MC3224i firmware-extraction study and blasty's 2024 Lexmark/WTM research. Those studies concern related products/builds and can suggest source-search terms, firmware stages and logging architecture. They do not establish this ARM64 OEM unit's pinout, voltage, OTP state, encryption policy, exploitable vulnerability or working recovery procedure. Earlier categorical README claims transferred those properties too far.

The exact chip and board/build match must precede any model-specific conclusion. No exploit, key-oracle operation, credential extraction, firmware modification or invasive storage operation was performed as part of the boot analysis.

## Primary mechanism references

- [Linux dm-verity](https://docs.kernel.org/admin-guide/device-mapper/verity.html)
- [Linux ramoops](https://docs.kernel.org/admin-guide/ramoops.html)
- [systemd journal storage](https://www.freedesktop.org/software/systemd/man/latest/journald.conf.html)
- [systemd socket units](https://www.freedesktop.org/software/systemd/man/latest/systemd.socket.html)
- [systemd pstore archival](https://www.freedesktop.org/software/systemd/man/latest/systemd-pstore.service.html)
- [U-Boot FIT packaging](https://docs.u-boot.org/en/latest/usage/fit/index.html)
- [Docker logging configuration](https://docs.docker.com/engine/logging/configure/)
- [Azure IoT Edge security manager](https://learn.microsoft.com/en-us/azure/iot-edge/iot-edge-security-manager)

Current online documentation explains mechanisms; it is not evidence of this OEM's undisclosed configuration. The annotated report contains additional kernel references and exact per-line evidence.
