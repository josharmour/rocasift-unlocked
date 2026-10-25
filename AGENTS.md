# Repository Guidelines

## Project Structure & Module Organization

This repository documents Roca Sifter / Lexmark Optra Compute 550 research. Public findings live in `docs/`; `README.md` tracks scope and next steps. There is no application or automated test suite. The following original evidence stays local and is ignored by Git:

- `FINDINGS.md`: device, API, network, and firmware observations.
- `BOARD-NOTES.md`: hardware layout, physical access notes, and open questions.
- `batch-289675-scans.json` and `manifest.csv`: scan snapshot and tabular inventory.
- `images/`: scan JPEGs named by batch item ID, such as `50952597.jpg`.
- `device/`: identity, endpoint snapshots, and encrypted device logs.
- `mitm/`: proxy experiment logs and capture files.
- `reference/`: vendor PDF manuals.

## Development & Validation Commands

There is no build system, package installation, or local application server. Run these inspection commands from the repository root:

```sh
python3 -m json.tool batch-289675-scans.json > /dev/null
python3 -m json.tool device/identity.json > /dev/null
rg --files images | wc -l
rg -n '\[O\]|\[I\]' FINDINGS.md
```

These validate JSON syntax, count image files, and locate evidence labels. Python 3 and ripgrep must be installed separately.

## Documentation Style & Naming Conventions

Use concise Markdown headings, fenced command examples, and relative artifact paths. Mark observations `[O]` and inferences `[I]`, following `FINDINGS.md`. Record collection dates, sources, and reproduction steps for new findings.

Preserve existing JSON formatting, field names, CSV headers, and item identifiers. Use descriptive lowercase hyphenated artifact names and `batch-<id>-scans.json` for additional snapshots. Keep original captures intact; save derived or redacted versions separately. No formatter or linter is configured.

## Testing Guidelines

Validation is artifact-based; no testing framework or coverage target exists. Parse changed JSON and CSV files, reconcile scan records with image filenames, and check newly collected images for readability. The documented batch baseline is 501 records and 501 JPEGs at 446×600. Record validation results and explain discrepancies when adding data.

## Commit & Pull Request Guidelines

Use short imperative commit subjects, such as `docs: clarify proxy capture findings`. Keep unrelated experiments separate. This repository is newly initialized; no longstanding commit convention exists.

Pull requests should describe the evidence added, collection method, affected artifacts, validation performed, and any linked issue. Include annotated photos for physical-layout claims when available.

## Sensitive Data & Device Changes

Exclude passwords, session cookies, authorization headers, and runtime secrets from shared artifacts. Review captures before publishing. Document device configuration changes and restoration steps; consult the recorded proxy failures before repeating experiments that may interrupt jobs.
