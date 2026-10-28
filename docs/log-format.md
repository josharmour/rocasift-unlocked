# Understanding the downloadable device logs

## Verified samples

Five log bundles downloaded from the device web interface (EWS) have been
parsed with OpenSSL as PKCS#7/CMS **EnvelopedData** containers. This is
encryption, not a hash or a simple text encoding.

| Bundle (download date) | Size (bytes) | Envelope |
| --- | --- | --- |
| 2026-10-21T022850Z | 6,431,694 | identical structure |
| 2026-10-24 (`device-logs.bin`) | 10,497,182 | identical structure |
| 2026-10-25T034641Z | 12,956,490 | identical structure |
| 2026-10-26T044249Z | 16,372,946 | identical structure |
| 2026-10-28T052208Z | 15,107,726 | identical structure |

Envelope structure is byte-for-byte consistent across all five samples and
across firmware 3.5.4 downloads days apart: same recipient certificate
reference, same algorithms, same indefinite-length ASN.1 encoding.

Observed fields (identical in every sample):

| Field | Value |
| --- | --- |
| Outer content type | `pkcs7-envelopedData` |
| Inner content type | `pkcs7-data` |
| Key transport algorithm | `rsaEncryption` (3072-bit RSA; 384-byte encrypted key block) |
| Content encryption algorithm | `aes-256-cbc`, 16-byte random IV per bundle |
| Recipient issuer | C=US, ST=KY, L=Lexington, O=Lexmark International, Inc., OU=**System BIOS**, CN=`padebug.lpdev.prtdev.lexmark.com`, email=`system-bios@lexmark.com` |
| Recipient certificate serial | `B7200FFE7A8AE643` (same in every bundle) |
| Ciphertext layout | contiguous 4096-byte AES blocks from offset ~686 to EOF |

Notes:

- The recipient certificate identifies the **Lexmark "System BIOS" /
  padebug** support infrastructure — the same subsystem named in the EWS
  log-download endpoint. The device only needs the recipient's *public*
  key to seal the bundle; the matching private key lives with Lexmark
  support tooling.
- The IV differs per download (fresh random IV each time), while the
  recipient/serial stays constant — consistent with the device sealing
  each export independently.
- Filename pattern `debug-logs-<UTC timestamp>Z.tgz.der` implies the
  plaintext payload is a **tar.gz archive** (`.tgz`) wrapped in a DER
  CMS envelope (`.der`). The inner archive layout is unverified until a
  bundle is decrypted.

## What that means

CMS encrypts the contents with a content-encryption key and encrypts that
key for the recipient. With this RSA key-transport form, normal decryption
requires the corresponding recipient private key. A public certificate or
the web-interface password alone does not provide that key. See
[RFC 5652, section 6](https://www.rfc-editor.org/rfc/rfc5652.html#section-6).

The format is fully parseable; obtaining readable log contents is the
unresolved part. We have not decrypted any payload. Do not assume an
accessible file can be decoded by renaming it, decompressing it, or applying
a hash-cracking tool.

## Reproduce the inspection

On a local copy of your own downloaded log bundle:

```sh
openssl asn1parse -inform DER -in debug-logs-YYYY-MM-DDTHHMMSSZ.tgz.der -i
```

This inspects the envelope; it does not decrypt it. Output contains large
ciphertext dumps — publish a reviewed metadata summary rather than the
complete output or binary.

## Research goals

- [x] Compare envelope metadata across repeat downloads — done: five
      samples, identical structure and recipient (2026-10-21 → 2026-10-28).
- [ ] Ask Roca/Lexmark for an owner-readable diagnostic export or supported viewer.
- [ ] Identify the device component that collects and encrypts the logs.
- [ ] Determine whether the original plaintext logs are accessible through supported diagnostics or authorized local access.
- [ ] If software inspection becomes possible (e.g. via firmware/rootfs obtained through authorized means), document certificate provisioning and bundle creation without publishing secrets.
- [ ] Build a metadata inspector and a decoder only for formats and keys legitimately available to owners.

The device may only need the recipient's public key to create the bundle.
Extracting firmware would not necessarily yield the private key needed to
decrypt existing downloads. Brute-forcing the observed encryption is not a
practical project goal.
