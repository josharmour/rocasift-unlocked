# Device surface inventory

Everything the Sifter exposes on the network, what each surface will tell you,
and what image metadata is visible. Historical observations on firmware 3.5.4
(build target `granite2v8-sifter`) on 2026-10-30, during and around live scan
jobs. Observations are marked `[O]`, inferences `[I]`.

The [later UART/diagnostic review](research/diagnostic-research-2026-10-30.md) qualifies binding, image-retention and console-access claims. Historical unknown-protocol probes below are recorded as prior experiments, not a recommendation to repeat them during scans.

Reproduce the event-bus captures with [`tools/bus-probe.py`](../tools/bus-probe.py).

## Network surfaces

| Port | Protocol | Auth | What it exposes |
| --- | --- | --- | --- |
| 80/tcp | HTTP | none | `301` redirect to HTTPS (`Server: webserver`) |
| 443/tcp | HTTPS | Basic `optra:<device password>` | EWS SPA + `/webservices/*` settings/diagnostics API |
| 5000/tcp | HTTP | **none** | FastAPI "Sifter Vision API" — card recognition |
| 5355/udp | LLMNR | none | Windows name resolution only |
| 9002/tcp | WebSocket (MessagePack) | **none** | Live node-graph event bus |
| 21586/tcp | TCP; application protocol unknown | unknown | Accepted connections stayed silent during the observed window; tested inputs caused closure; no handshake established |
| 21587/tcp | Raw TCP (MessagePack) | **none** | Same event stream as 9002, server speaks first |
| 50800/tcp | TCP (MDCIF) | unknown | Listener announced at boot; prior LAN attempts refused; binding and protocol unresolved |

Also present but not network-reachable: the rear USB-B device port (composite
HID + vendor-specific + printer class, inert during cloud-driven jobs) and the
JRIP1 UART output (115200 8N1; interactive receive/login not established on this unit).

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

Tested unknown paths fell through to the SPA shell. No file/image retrieval
endpoint was found in those tests; that is not an exhaustive proof none exists.

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
Prior LAN attempts were refused. Loopback/container binding, service state and
filtering remain competing explanations; neither the binding nor ownership of
image handles is established. The log proves TCP, not HTTP or a request format.
Saved service/client definitions are needed before choosing a supported access path.

### Port 21586 — silent, input-rejecting `[O]`

Accepts TCP and then says nothing: a connection held open for 15 s during an
active scan received zero bytes. The tested inputs closed it within ~5 ms — historical tests included
every byte value `0x00`–`0x0f`, `A`–`Z`, `{}[]<>`, `0x7f`, `0xff`, plus HTTP
requests, a TLS ClientHello, and MessagePack payloads. Multi-byte payloads that
leave unread data in the socket produce a TCP reset rather than a clean FIN.
UDP on the same port is silent. No handshake was found. An internal consumer is a hypothesis, not an identified
service or proof that all possible input is rejected.

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

### Card lifecycle `[O]`

One sheet, deduplicated across the two channels (every event is delivered on
both; a WebSocket connection that starts late can miss frames):

```
nodeAdded    PageQueue/<id>/eject
nodeChanged  PageQueue/<id>/Front/state   Scanning
nodeChanged  PageQueue/<id>/Back/state    Scanning
nodeChanged  PageQueue/<id>/foil          NotDetected | Detected
nodeChanged  PageQueue/<id>/Front/state   Safe
nodeChanged  PageQueue/<id>/Back/state    Safe
nodeChanged  PageQueue/<id>/Front/Image/{composition,handle,mediaWindow/*,outputCanvas/*,compression}
nodeChanged  PageQueue/<id>/Back/Image/{...}
nodeChanged  PageQueue/<id>/Front/state   Ejected
nodeChanged  PageQueue/<id>/Back/state    Ejected
nodeRemoved  PageQueue/<id>
```

`Image` fields arrive as individual leaf updates rather than one object, so a
single sheet produces roughly twenty `Image` messages. `PageQueue/ready` reads
`true` between sheets. `Status/SideCountPermanent/adfFront` and `adfBack`
increment by one per side scanned.

Page ids advance by two per sheet (`19`, `21`, … `67`), which suggests an id is
consumed per side internally even though front and back share one node.

A 60-second capture during a live run produced **494 messages across 25 sheets**:
445 `nodeChanged`, 25 `nodeAdded`, 24 `nodeRemoved`. The raw TCP channel carried
345 of them and the WebSocket channel 149 — the WebSocket connection was opened
later and missed the earlier frames.

The `Image` node announces image geometry and a handle; it does not return pixels:

```json
{"composition": "Rgb24", "handle": 0,
 "mediaWindow": {"x": -900.0, "y": 0.0, "w": 1800.0, "h": 2020.0,
                 "xRes": 600.0, "yRes": 600.0},
 "outputCanvas": {"x": -420.0, "y": -75.0, "w": 870, "h": 1170,
                  "xRes": 300.0, "yRes": 300.0},
 "compression": "Jpeg"}
```

`handle` is `0` for the front side and `1` for the back. There is no path, URL,
byte count, or payload — only geometry and a numeric handle. Its owning process, backing store and
lifetime remain unverified.

## Image geometry and retrieval evidence

The descriptors and downloaded thumbnails expose these geometries; the first
two rows are metadata, not a verified read of the corresponding image bytes:

| Layer | Size | Format | Reachable? |
| --- | --- | --- | --- |
| Advertised sensor media window | 1800 × 2020 @ 600 dpi | RGB24 | No — handle only |
| Advertised output canvas | 870 × 1170 @ 300 dpi | JPEG | No — handle only |
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

**No tested local endpoint returned full-resolution scan bytes.** Portal
thumbnail export works. The available local interfaces expose metadata or
consume supplied images; retained full-resolution data and its location remain
unverified:

- the event bus announces geometry and foil detection per page,
- the Vision API consumes images but never serves them,
- no EWS file/image retrieval route was found in the inspected surface,
- MDCIF binding and image-retrieval capability remain unknown,
- historical USB observations showed no job traffic; UART output did not establish interactive access.

Next evidence should come from a supported diagnostic export, documented image
API or explicitly authorized application mount/log access. The exact trust
store, image ownership, persistence and supported full-resolution export route
remain unresolved; prior certificate rejection does not establish the complete
trust-store contents.

## What this means for exports

Exports built from the seller portal contain the **446 × 600 thumbnail**, which is
adequate for identification but not for condition grading or resale listings that
want detail. The live event bus adds metadata the portal does not expose —
per-page foil detection before recognition runs, plus exact scan geometry — but it
cannot supply pixels.
