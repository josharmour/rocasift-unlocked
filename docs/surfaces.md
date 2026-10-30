# Device surface inventory

Everything the Sifter exposes on the network, what each surface will tell you,
and where the scan images actually live. Collected read-only on firmware 3.5.4
(build target `granite2v8-sifter`) on 2026-10-30, during and around live scan
jobs. Observations are marked `[O]`, inferences `[I]`.

Reproduce the event-bus captures with [`tools/bus-probe.py`](../tools/bus-probe.py).

## Network surfaces

| Port | Protocol | Auth | What it exposes |
| --- | --- | --- | --- |
| 80/tcp | HTTP | none | `301` redirect to HTTPS (`Server: webserver`) |
| 443/tcp | HTTPS | Basic `optra:<device password>` | EWS SPA + `/webservices/*` settings/diagnostics API |
| 5000/tcp | HTTP | **none** | FastAPI "Sifter Vision API" — card recognition |
| 5355/udp | LLMNR | none | Windows name resolution only |
| 9002/tcp | WebSocket (MessagePack) | **none** | Live node-graph event bus |
| 21586/tcp | TCP | none | Accepts connections, sends nothing, ignores HTTP |
| 21587/tcp | Raw TCP (MessagePack) | **none** | Same event stream as 9002, server speaks first |
| 50800/tcp | TCP (MDCIF) | — | Device-control server; **loopback-bound**, refused from LAN |

Also present but not network-reachable: the rear USB-B device port (composite
HID + vendor-specific + printer class, inert during cloud-driven jobs) and the
JRIP1 UART console (115200 8N1, TX-only on production units).

### EWS — port 443 `[O]`

Authenticated with `Authorization: Basic base64("optra:" + password)`. Every
`/webservices/*` path returns `401` without credentials. Documented endpoints:

```
POST /login {password}
GET  /webservices/settings/<key[,key...]>     PUT /webservices/settings/
GET  /webservices/logs                        (PKCS#7 sealed to Lexmark support)
GET  /webservices/diagnostics/screenshot      (500: no display attached)
GET  /webservices/diagnostics/external/urls
GET/PUT/DELETE /webservices/proxy             POST /webservices/proxy/test
POST /webservices/password {password}
GET  /webservices/wireless/{interface,networks,psk}
```

Unknown paths fall through to the SPA shell — there is no hidden file or image
endpoint. The endpoint surface does not change while a job runs.

### Vision API — port 5000 `[O]`

Unauthenticated FastAPI service, self-documenting at `/openapi.json`. Exactly
four routes:

```
GET  /ram                        -> {"ram_usage": <percent>}
POST /sifter/initialize          -> start a recognition session for a game
POST /sifter/recognize_card      -> multipart image in, catalog match out
POST /sifter/reset               -> tear the session down
```

`recognize_card` **accepts** an image; nothing on this service **returns** one.
`CropInfo` is four integers plus a score — crop geometry, not pixels. Probing
`/images`, `/scans`, `/capture`, `/frame`, `/snapshot`, `/files`, `/media` and a
dozen similar names returns `404` JSON.

### MDCIF — port 50800 `[O]`

The boot console prints `MDCIF: ... Listening for TCP connection on port 50800`.
Connections from the LAN are refused while every other listed port accepts, so
the listener is bound to loopback or a container network. This is the process
that owns the scan pipeline's image handles; reaching it requires code
execution on the device.

## Event bus protocol — ports 9002 and 21587 `[O]`

Both ports carry the same MessagePack stream. `21587` is raw TCP and speaks
first; `9002` is a WebSocket server that completes a handshake on any path and
then sends binary frames of the same payloads. Neither requires authentication.

Envelope: a three-element array.

```
[2, "<event>", [ <payload> ]]
```

Events observed: `nodeChanged`, `nodeAdded`, `nodeRemoved`. The payload is a
map of node name to node body. Two node types appear during a scan:

```
PageQueue/<page id>/Front/{state, Image}
PageQueue/<page id>/Back/{state, Image}
PageQueue/<page id>/foil          -> "Detected" | "NotDetected"
PageQueue/ready                   -> true when the feeder is idle
Status/SideCountPermanent/adfFront, adfBack   -> lifetime sheet counters
```

Page states observed in order for each sheet: `Scanning` → `Safe` → `Ejected`,
then `nodeRemoved`. A typical card produces roughly a dozen messages across both
sides plus two counter updates.

The `Image` node is the interesting one — it announces that pixels exist:

```json
{"composition": "Rgb24", "handle": 0,
 "mediaWindow": {"x": -900.0, "y": 0.0, "w": 1800.0, "h": 2020.0,
                 "xRes": 600.0, "yRes": 600.0},
 "outputCanvas": {"x": -420.0, "y": -75.0, "w": 870, "h": 1170,
                  "xRes": 300.0, "yRes": 300.0},
 "compression": "Jpeg"}
```

`handle` is `0` for the front side and `1` for the back. There is no path, URL,
byte count, or payload — only geometry and a handle into the device's own image
store.

## Where the scan images actually live

Three different resolutions exist at three different layers:

| Layer | Size | Format | Reachable? |
| --- | --- | --- | --- |
| Sensor media window (in memory) | 1800 × 2020 @ 600 dpi | RGB24 | No — handle only |
| Output canvas (JPEG-compressed) | 870 × 1170 @ 300 dpi | JPEG | No — handle only |
| Portal thumbnail (`imageUrl`) | 446 × 600 | JPEG | Yes — seller session |

The portal's `thumb.jpg` is a ~0.5× downscale of the output canvas (aspect ratios
match to three decimals). Batch items carry exactly one image field, `imageUrl`,
and it always points at `.../images/<batch>/<item>/thumb.jpg`. Ten candidate
larger variants (`full.jpg`, `original.jpg`, `large.jpg`, `thumb@2x.jpg`,
extensionless paths, query-string sizes) all return `404`. There is no scan or
image endpoint on the seller API either (`/batch/<id>/scans`,
`/batch/<id>/images`, `/scans?batchId=` → `404`).

The device also uploads to object storage — its own reachability list includes
`https://bucket.optra.com:443`, an S3 bucket behind CloudFront that answers
anonymous requests with `403 AccessDenied`. Keys are not guessable and listing is
denied.

### Conclusion

**No network surface returns scan image bytes.** The pixels exist on the device
(behind an internal handle) and in vendor object storage (behind credentials),
but every owner-reachable interface exposes metadata only:

- the event bus announces geometry and foil detection per page,
- the Vision API consumes images but never serves them,
- EWS has no file or image route,
- MDCIF is loopback-bound,
- USB is inert during jobs and UART is TX-only.

Getting full-resolution scans would require one of: code execution on the device
to talk to MDCIF or read its image store; a trusted TLS position to capture the
upload (the device trusts only Lexmark/Azure roots); or vendor storage
credentials. None of those are available to an owner today.

## What this means for exports

Exports built from the seller portal contain the **446 × 600 thumbnail**, which is
adequate for identification but not for condition grading or resale listings that
want detail. The live event bus adds metadata the portal does not expose —
per-page foil detection before recognition runs, plus exact scan geometry — but it
cannot supply pixels.
