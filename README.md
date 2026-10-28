# rocasift-unlocked

**Help make the Roca Sifter work with the platforms its owners choose.**

I own a Roca Sifter, and I want to use its scanning and sorting hardware with more than TCGplayer. My goal is to make it useful with **SortSwift, Card Dealer Pro, TCGTracking**, and other collection, inventory, and selling tools.

If you have one of these devices, join in. We need owners willing to compare observations, developers who can build exporters and integrations, and people with experience in embedded Linux, hardware, and diagnostic formats. Even documenting a repeatable problem or a successful export helps.

## What “unlocked” means here

The long-term goal is owner-controlled scanning, access to our card images and data, and the ability to connect the hardware to other workflows. Start with reliable exports; investigate local control and offline operation as separate milestones.

**This is an early research project. No firmware unlock or working third-party integration is available yet.** SortSwift, Card Dealer Pro, and TCGTracking are desired integration targets, not confirmed partners or supported integrations. This project is independent of Roca, Lexmark, and TCGplayer.

## Research already collected

- [Original findings, redacted for sharing](docs/research/FINDINGS.md): platform identification, observed API routes, cloud dependencies, and proxy experiments.
- [Board research notes](docs/research/BOARD-NOTES.md): physical layout and questions for a verified board survey.
- [Scan-image export workflow](docs/scan-exports.md): an existing local export contains 501 JPEGs and a card manifest, including an unidentified card.
- [Current device findings](docs/device-findings.md): what worked, what failed, and what remains uncertain.
- [Encrypted log format](docs/log-format.md): confirmed container and algorithms, plus a plan for owner-readable diagnostics.
- [USB probe runbook](docs/usb-probe-runbook.md): how to characterize the Sifter's USB device port from Linux (descriptor dump, passive vendor-interface listen, printer-class test).

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
