# rocasift-unlocked

**Help make the Roca Sifter work with the platforms its owners choose.**

I own a Roca Sifter, and I want to use its scanning and sorting hardware with more than TCGplayer. My goal is to make it useful with **SortSwift, Card Dealer Pro, TCGTracking**, and other collection, inventory, and selling tools.

If you have one of these devices, join in. We need owners willing to compare observations, developers who can build exporters and integrations, and people with experience in embedded Linux, hardware, and diagnostic formats. Even documenting a repeatable problem or a successful export helps.

## What “unlocked” means here

The long-term goal is owner-controlled scanning, access to our card images and data, and the ability to connect the hardware to other workflows. Start with reliable exports; investigate local control and offline operation as separate milestones.

**This is an early research project. No firmware unlock or working third-party integration is available yet.** SortSwift, Card Dealer Pro, and TCGTracking are desired integration targets, not confirmed partners or supported integrations. This project is independent of Roca, Lexmark, and TCGplayer.

## Latest diagnostic research

[Complete UART analysis and diagnostic research](docs/research/diagnostic-research-2026-10-30.md) covers every saved boot line, log destinations, internal settings/services, missing-image recovery questions, and access prerequisites. The report distinguishes observations from hypotheses and corrects earlier claims about loopback binding, encryption and debug access.

## Headline findings (October 2026)

Original research, first published here:

- **Local card-recognition API discovered** (`docs/vision-api.md`): the device runs an unauthenticated FastAPI service on port 5000 — `POST /sifter/recognize_card` accepts a card image and returns full TCGplayer catalog identification (name, set, number, rarity, `tcgp_catalog_code`) **on-device in ~0.6 s**, no cloud or account required. Sessions can be initialized and reset locally (`/sifter/initialize`, `/sifter/reset`).
- **Authenticated settings API mapped**: `GET /webservices/settings/all` exposes 121 device settings; `PUT /webservices/settings/` changes them (verified by toggling the hidden `SettingsPort8080` flag). Reveals an on-board Hailo AI accelerator, 4 GB RAM, TPM, eMMC health telemetry, and a custom firmware-pull URL setting.
- **Job stalls instrumented**: sampled host telemetry remained responsive during some stalled jobs while the portal reported "in progress." The initiating cause remains unproved; acquisition, upload and cloud acknowledgements need correlation for the same scan.
- **USB device port characterized** (`docs/usb-probe-runbook.md`): enumerates as a Lexmark composite device (vendor "Scan" interface + printer class + HID); no network gadget on current firmware; port is inert during jobs. Linux probe tooling included.
- **Board surveyed** (`docs/research/BOARD-NOTES.md`): Lexmark P/N 10U9020 REV 4 mainboard, unpopulated 6-pin JPRG1 programming header (ground pin identified), Infineon TPM 2.0, test points — with photos.
- **Encrypted log format documented** (`docs/log-format.md`): downloads are CMS-enveloped AES-256 bundles sealed to Lexmark support; structure verified across five samples.
- **Platform research reviewed**: this device reports an ARM64 `mv6270 Cobalt Edge` model, U-Boot 2022.01, Linux 6.12.54 and Lexmark Yocto. Related NCC Group and blasty research provides hypotheses; this unit's encryption, OTP/JTAG policy and UART receive path are not established by those studies. Its captured root mapping uses dm-verity/SquashFS.
- **Live scan event bus decoded** (`docs/surfaces.md`): two unauthenticated MessagePack channels (ports 9002 and 21587) stream the scan pipeline's node graph in real time — per-page front/back state, foil detection, and the geometry of each captured image (1800×2020 @ 600 dpi in, 870×1170 @ 300 dpi JPEG out). The bus announces images but never carries their bytes.
- **Device identity refined** (`docs/research/FINDINGS.md` §10f): machine type **8085-001** (unpublished OEM variant — public docs key to 8080), unit P/N 10U0900-003, radio = AzureWave AW-CM467 WiFi/BT5.0 module ("Contains FCC ID: TLZ-CM467").

## Progress

| Milestone | Status |
| --- | --- |
| Identify platform & document local API surface | ✅ done |
| Export scans + manifest (501 images) | ✅ done |
| Local card recognition via Vision API | ✅ working |
| Local sift session control (initialize/reset) | ✅ working |
| Diagnose job-stall failure mode | ✅ instrumented |
| Map device settings & hidden services | ✅ done |
| UART / console access | ✅ JRIP1 output captured at 115200 8N1; interactive input/login remains unproved. Complete saved-capture analysis is available. |
| Motor/feed actuation control | 🔍 Event bus decoded (9002/21587); 21586 protocol unresolved; MDCIF announces TCP 50800, with binding/access unresolved. |
| Full-resolution scan images | ⏳ Descriptors advertise larger geometry; no owner-readable full-resolution payload or retention policy demonstrated — see `docs/surfaces.md`. |
| Owner skill container deployment | 📝 Prototype drafted (`skills/sifter-export/`); installation permission and diagnostic mounts/APIs remain unverified. |
| Firmware extraction / root shell | ⏳ No working owner-accessible root shell or extraction route demonstrated. |
| End-to-end third-party integration demo | ⏳ next |

## Research already collected

- [Original findings, redacted for sharing](docs/research/FINDINGS.md): platform identification, observed API routes, cloud dependencies, and proxy experiments.
- [Board research notes](docs/research/BOARD-NOTES.md): physical layout and questions for a verified board survey.
- [Scan-image export workflow](docs/scan-exports.md): an existing local export contains 501 JPEGs and a card manifest, including an unidentified card.
- [Current device findings](docs/device-findings.md): what worked, what failed, and what remains uncertain.
- [Encrypted log format](docs/log-format.md): confirmed container and algorithms, plus a plan for owner-readable diagnostics.
- [USB probe runbook](docs/usb-probe-runbook.md): how to characterize the Sifter's USB device port from Linux (descriptor dump, passive vendor-interface listen, printer-class test).
- [Device surface inventory](docs/surfaces.md): every network port, protocol, and auth requirement, the event-bus message format, and where scan images actually live.
- [Sifter Vision API](docs/vision-api.md): the local card-recognition service on port 5000 — submit a card image, get TCGplayer catalog identification on-device.

Original account captures, card images, device identifiers, credentials, and vendor PDFs are kept local. The public notes preserve useful findings without publishing those files.

## Goals

- [ ] **Export every scanned card:** download images and metadata, include unidentified cards, preserve scan order, and resume interrupted exports.
- [ ] **Define a portable format:** document IDs, image paths, card attributes, confidence, and bin/sequence information in CSV/JSON.
- [ ] **Build platform adapters:** determine each target platform's supported imports or APIs, then test mappings with SortSwift, Card Dealer Pro, and TCGTracking users.
- [ ] **Understand the log bundle:** document its encryption envelope and identify a supported way for owners to obtain readable diagnostics.
- [ ] **Map the scan pipeline:** establish where images are captured, identification happens, and bin decisions are made; distinguish local work from cloud dependencies.
- [ ] **Investigate local control:** determine whether documented interfaces or owner-accessible software can start scans and return results independently of TCGplayer.
- [ ] **Document the hardware:** verify components, interfaces, and diagnostic access using actual board evidence.
- [ ] **Establish backup and recovery:** seek vendor firmware, record versions, and verify recovery before attempting firmware changes.
- [ ] **Prove an end-to-end alternative workflow:** scan cards, preserve their physical order, and import usable results into another platform. Track offline operation separately until demonstrated.

## Join the effort

[Open an issue](https://github.com/josharmour/rocasift-unlocked/issues) with your use case, the platform you want to connect, or a finding you can reproduce. Tell us your firmware version and what you tested; omit serial numbers, passwords, and account details.

Have an exporter, Chrome extension, hardware photos, or integration experience? Open a pull request or share a public project link. We would especially like to compare notes with owners already building tools, including the author of [this community discussion](https://www.reddit.com/r/magicTCG/comments/1xe1agl/roca_sifter_what_now/).

Read [CONTRIBUTING.md](CONTRIBUTING.md). Label observations and hypotheses separately, preserve original evidence locally, and document recovery steps for experiments that change the device.
