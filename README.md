# rocasift-unlocked

Independent research into Roca Sifter data portability, scan-image exports, and device behavior. This is an early research notebook, not an unlocked firmware release or an official Roca/TCGplayer project.

## What we can contribute

- A documented route from scanned card records to their individual JPEGs.
- A completed local export of 501 scan images, including an unidentified card.
- Device-management observations and unsuccessful proxy experiments, with limitations recorded.
- A practical roadmap for a resumable exporter and shared troubleshooting evidence.

Start with [scan exports](docs/scan-exports.md), [device findings](docs/device-findings.md), and [contributing](CONTRIBUTING.md).

## Status

As of October 24, 2026, this repository publishes curated documentation only. No downloader, Chrome extension, firmware image, or device unlock is included. The original captures, account data, card images, and vendor PDFs remain local and are ignored by Git.

## Next steps

- [ ] Build a resumable downloader with a manifest and image validation.
- [ ] Verify batch pagination and authenticated export behavior on fresh jobs.
- [ ] Include both matched and unidentified cards, preserving scan order.
- [ ] Investigate a browser extension that uses the owner's signed-in session.
- [ ] Document failures with device lights, portal messages, and timestamps.
- [ ] Verify hardware details against board photos and vendor documentation.

## Community research

[u/roadtripsarefun's discussion](https://www.reddit.com/r/magicTCG/comments/1xe1agl/roca_sifter_what_now/) describes personal Chrome extensions for photo/data exports and a dashboard. We have not located a public release or reviewed that code. Contributions or links from the author would be welcome.

Use your own device and account. Never include passwords, session cookies, authorization headers, or unredacted captures in issues or pull requests.
