# Privileges to request for sifter-export

From docs.optra.com/skills/privileges — request the minimum set that lets
the container read device data and write removable media:

| Privilege | Why |
| --- | --- |
| File system volumes | Read the scan-pipeline output directories and device state |
| Removable media | Write exports directly to a USB stick in the USB-A host port (alternative to network POST) |

Deliberately NOT requested (keep the approval case simple):
- GPIO, audio, camera (not needed for export)
- Elevated OS capabilities / network raw sockets

If the portal requires justification text per privilege:
- File system: "Export the device owner's scan results and diagnostic data
  to their own storage, per the platform's data-ownership goals."
- Removable media: "Allow direct export to a USB drive attached to the
  device's host port."

Fallback if file-system privilege is denied: run the export agent with
only removable-media privilege and have the workflow's earlier stage
(or IoT messages) deliver the data.
