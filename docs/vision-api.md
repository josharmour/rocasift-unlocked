# Sifter Vision API — local card recognition on port 5000

Discovered October 27–28, 2026. This is the device's card-recognition
engine, exposed on the LAN at `http://<device-ip>:5000` as a FastAPI
(uvicorn) service titled **"Sifter Vision API"** (`x-api-version: 1.8.10`).

Self-documenting: `GET /openapi.json`, interactive docs at `/docs` and
`/redoc`. **No authentication required.**

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/ram` | RAM usage percentage |
| POST | `/sifter/initialize` | Initialize a sift session |
| POST | `/sifter/recognize_card` | Recognize a card from an image |
| POST | `/sifter/reset` | Reset sift state |

## `POST /sifter/recognize_card`

Multipart form:

| Field | Type | Notes |
| --- | --- | --- |
| `file` | binary (required) | Card image (JPEG) |
| `is_foil` | bool (required) | Foil finish hint |
| `is_pre_cropped` | bool | Default false — service crops |
| `half_card` | int | Default 0 |

Response (verified against a real scan from the device's own export):

```json
{
  "card": {
    "card_id": "31b99bd7fea84e2cad4fd83ea730ce9d",
    "name": "Cruel Finality",
    "set": "Aether Revolt",
    "number": "54",
    "rarity": "C",
    "color": "4",
    "card_type": "Instant",
    "card_subtype": "4",
    "tcgp_catalog_code": "126467",
    "cat2_id": "KbRE5TvSCWLozsSVueDTWWA",
    "finish_modifier": ""
  },
  "recognition_score": 0.555,
  "set_score": 1.0,
  "rec_time": 0.438,
  "full_time": 0.592,
  "alternatives": [],
  "crop_info": null,
  "upside_down": false,
  "detail": "Card recognized successfully."
}
```

Recognition completed in **0.59 s** on-device — fast enough for real-time
sorting workflows driven by an external controller.

## Score semantics — read this before building on it

`detail` is **not** a success indicator. It reads
`"Card recognized successfully."` on every response, including for input
that is not a card. `recognition_score` is the only quality signal, and it
can be negative:

| Input | Returned | Score |
| --- | --- | --- |
| real card | correct name / set | 0.49 – 0.72 |
| card back | *Back of a Magic Card* / `Sorting Robotics Extra` | −0.027 |
| blank gray JPEG | *Find the Assassin (cont'd)* / `Assassin's Creed Minigames` | 0.185 |

The device carries synthetic catalog sets (`Sorting Robotics Extra`,
`Assassin's Creed Minigames`) that act as catch-all classes for non-card
imagery, with non-numeric `tcgp_catalog_code` values such as
`Sorting Robotics Extra-Back of a Magic Card.jpg`.

Threshold on `recognition_score` (≈0.3 separated real from non-card input
in a six-sample test, not yet calibrated) and reject non-numeric catalog
codes. Verified 2026-10-30 against firmware 3.5.4, `x-api-version: 1.8.10`.

## Why this matters

This is the device's core function callable locally: any tool on the same
network can submit a card image and receive TCGplayer catalog identification
(`tcgp_catalog_code`, `cat2_id`) without the cloud, a TCGplayer account, or
the Roca workflow. Combined with the camera/scan pipeline, this is the
foundation for owner-controlled scanning and third-party integrations
(SortSwift, Card Dealer Pro, TCGTracking).

## Discovery context

Found during a follow-up port scan after enabling the hidden
`SettingsPort8080` setting via the authenticated settings API
(`PUT /webservices/settings/`). Whether that setting gates this service or
port 5000 was already listening is not yet confirmed — a reboot test with
the setting off would settle it.

## Example client

```python
import urllib.request, uuid

def recognize(image_bytes, is_foil=False):
    b = uuid.uuid4().hex
    part = lambda n, v: f'--{b}\r\nContent-Disposition: form-data; name="{n}"\r\n\r\n{v}\r\n'.encode()
    body = (part("is_foil", str(is_foil).lower())
          + part("is_pre_cropped", "false")
          + part("half_card", "0")
          + (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="c.jpg"\r\n'
             f'Content-Type: image/jpeg\r\n\r\n').encode()
          + image_bytes + f"\r\n--{b}--\r\n".encode())
    req = urllib.request.Request("http://<device-ip>:5000/sifter/recognize_card",
        data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    return urllib.request.urlopen(req, timeout=60).read()
```
