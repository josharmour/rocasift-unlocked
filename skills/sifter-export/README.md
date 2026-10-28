# sifter-export — an Optra Edge skill for owner-controlled data export

A minimal ARM64 Docker skill for Optra Edge devices (Roca Sifter /
Lexmark Optra Compute 550). Runs as a sandboxed container with
file-system + removable-media privileges and exports chosen directories
to an owner-controlled endpoint.

This is the vendor-sanctioned route to owner data access: no firmware
modification, fully reversible, deployed through the Optra portal.

## Files

- `Dockerfile` — ARM64 image, tiny footprint
- `export-agent.py` — the agent: tars target paths, POSTs to endpoint,
  emits status via stdout (portal charts) 
- `docker-compose.yml` — alternative packaging as a Compose skill
- `PRIVILEGES.md` — the privilege set to request in the portal manifest

## Build and push

```sh
docker buildx build --platform linux/arm64 -t <you>/sifter-export:0.1.0 --push .
```

## Portal manifest sketch

- Type: Docker Image skill
- Image: `<you>/sifter-export:0.1.0`
- Inputs:
  - `TARGET_PATHS` (Text) — space-separated paths to export
  - `ENDPOINT_URL` (Text) — HTTPS endpoint that accepts POST multipart
  - `INTERVAL_SECONDS` (Text) — poll interval; 0 = run once per start
  - `AUTH_TOKEN` (Password) — bearer token for the endpoint
- Outputs:
  - `last_export_bytes` (Number)
  - `last_export_status` (String) — ok / error:<detail>
  - `files_seen` (Number)
- Privileges: file system volumes, removable media (see PRIVILEGES.md)

## Open questions (tracked in FINDINGS.md §10b)

1. Can an owner claim a Roca/TCGplayer-provisioned Sifter into their own
   Optra portal org?
2. Do third-party skills get privileges without Lexmark review?
3. Does the device's IoT Edge runtime pull from public Docker Hub?
