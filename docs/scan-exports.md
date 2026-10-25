# Scan image exports

Research date: October 24, 2026. These observations come from one owner's local export; they are not a supported or stable public API contract.

## Confirmed in the saved export

[O] The local snapshot contains 500 matched records and one unidentified record, with 501 JPEG files. Each filename is the scan's `batchItemId`; `sequenceId` records scan order. Card names alone are unsuitable identifiers because multiple physical cards can share a name.

[O] Saved records include an `imageUrl` of this form:

```text
https://ql-api.tcgplayer.com/images/<batchId>/<batchItemId>/thumb.jpg
```

[O] The captured images were reported as 446 × 600 pixels. Alternate full-size routes tested during the investigation did not produce higher-resolution images. This does not prove that higher-resolution originals do not exist internally.

## Observed retrieval flow

The earlier session used the owner's authenticated seller session to access:

```text
GET  /batch/<batchId>
POST /search/batch/<batchId>/matched-items
POST /search/batch/<batchId>/unidentified-items
```

The search requests used `page` and `pageSize`. Before implementing fresh retrieval, verify page numbering, response structure, total-count semantics, and completion behavior in an authorized session. Do not guess item IDs or assume that the first page is the full batch.

Download each record's image, save it as `<batchItemId>.jpg`, and retain a CSV mapping IDs to sequence, name, set, condition, printing, language, and image URL. Keep unmatched records even when name and set are null.

## Exporter acceptance criteria

- Explicit batch selection and both record categories.
- Scoped authentication that never appears in logs or exported files.
- Resume existing downloads, bounded retries, and rate-limit backoff.
- Validate downloaded images and reject login/error pages.
- Reconcile expected records, unique IDs, successful images, and failures.
- Preserve original evidence and report partial exports clearly.

TCGplayer also describes individual image saving and CSV exports on its [official Sifter page](https://seller.tcgplayer.com/roca-sifter).
