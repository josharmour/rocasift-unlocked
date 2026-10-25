# Understanding the downloadable device logs

## Verified sample

On October 24, 2026, OpenSSL parsed the locally retained `device/device-logs.bin` (10,497,182 bytes) as a PKCS#7/CMS **EnvelopedData** container. This is encryption, not a hash or a simple text encoding.

Observed fields:

| Field | Value |
| --- | --- |
| Outer content type | `pkcs7-envelopedData` |
| Inner content type | `pkcs7-data` |
| Key transport algorithm | `rsaEncryption` |
| Content encryption algorithm | `aes-256-cbc` |
| Recipient issuer organization | Lexmark International, Inc. |
| Recipient issuer common name | `padebug.lpdev.prtdev.lexmark.com` |

These issuer fields identify the certificate used to address the recipient; they do not embed its private key or prove exactly where that key is held. The sample uses indefinite-length ASN.1 encoding, which OpenSSL accepts with `-inform DER`.

## What that means

CMS encrypts the contents with a content-encryption key and encrypts that key for the recipient. With this RSA key-transport form, normal decryption requires the corresponding recipient private key. A public certificate or the web-interface password alone does not provide that key. See [RFC 5652, section 6](https://www.rfc-editor.org/rfc/rfc5652.html#section-6).

The format is already parseable; obtaining readable log contents is the unresolved part. We have not decrypted the payload or identified its internal archive format. Do not assume an accessible file can be decoded by renaming it, decompressing it, or applying a hash-cracking tool.

## Reproduce the inspection

On a local copy of your own downloaded log bundle:

```sh
openssl asn1parse -inform DER -in device-logs.bin -i
```

This inspects the envelope; it does not decrypt it. Output can contain identifiers and large ciphertext dumps. Publish a reviewed metadata summary rather than the complete output or binary.

## Research goals

- [ ] Compare envelope metadata across firmware versions and repeat downloads.
- [ ] Ask Roca/Lexmark for an owner-readable diagnostic export or supported viewer.
- [ ] Identify the device component that collects and encrypts the logs.
- [ ] Determine whether the original plaintext logs are accessible through supported diagnostics or authorized local access.
- [ ] If software inspection becomes possible, document certificate provisioning and bundle creation without publishing secrets.
- [ ] Build a metadata inspector and a decoder only for formats and keys legitimately available to owners.

The device may only need the recipient's public key to create the bundle. Extracting firmware would not necessarily yield the private key needed to decrypt existing downloads. Brute-forcing the observed encryption is not a practical project goal.
