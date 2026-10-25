> Public copy of the local board notes. Hardware access is unverified; speculative connection instructions have been replaced with explicit research questions. Vendor reference PDFs are retained locally.

# Roca Sifter — Board Layout & Physical Access Notes
Researched 2026-10-24. Sources: official Lexmark Optra docs (in reference/),
official chassis diagrams (analyzed), spec sheets, live device.

## The compute unit inside the Sifter

The Sifter enclosure contains a standard **Lexmark Optra Compute 550**
(machine type **8080**, models 001–004 per the user guide notices) mounted in
the base, plus the card tower/rollers which are consumables and irrelevant here.

### External anatomy of the Compute 550 (confirmed from official diagrams)

FRONT PANEL:
- Power button (round, right end)
- Setup button (round) — enroll (brief press) / factory reset (hold while powering on)
- Hex stud = chassis ground point
- Connector cluster (left half):
  - RJ-45 Ethernet + 2 indicator LEDs (left=link, right=activity)
  - USB Type-A HOST port — flash drive or MarkNet adapter
  - Narrow slot = **USB DEVICE port** — proposed path to test for a
    network gadget exposing the EWS; not verified in this investigation

REAR:
- IEC C14 AC inlet between two retaining screws
- Rack-mount ears with slotted holes; folded sheet-metal seams everywhere

NO external UART/JTAG/debug headers exist on the stock enclosure. [O]

### Internals (platform facts)

- SoC: quad-core ARM v8, ~20 GFLOP, 2GB RAM (32-bit build), exact part unconfirmed
- Storage: 16GB eMMC (soldered BGA)
- WiFi: Lexmark house module (both wired+wired MACs are Lexmark OUIs 78:8C:77 / 00:84:ED)
- OS: Poky Linux (Yocto), secure boot, Azure IoT Edge runtime, Docker skills
- Lithium coin cell present (RTC) — caution when handling

## Access plan (ordered by invasiveness)

### Phase 0 — zero tools, do first
1. **Regulatory label → FCC ID.** The FCC ID is printed on the device label
   (Sifter base or Compute 550 case). Lexmark machine type is 8080; grantee
   code TBD. The FCC filing contains **internal photos of the PCB** — every
   header, pad, and silkscreen label visible. This is the cheapest way to see
   the board before touching a screwdriver. FCC databases are bot-walled from
   this workstation, so read the ID off the label and I'll pull the filing.
2. **USB device port → EWS over USB.** Plug the USB-B port into a computer;
   device should enumerate as a network gadget; EWS reachable at its gadget IP.
   Same authenticated EWS as LAN — no new data, but confirms the gadget path.

### Phase 1 — open the Sifter enclosure
- Lid opens via the button on the right side; remove card tower, weight, hopper.
- The Compute 550 sits in the base; note cable routing before disconnecting
  (power, Ethernet, and any internal USB/photodiode harnesses).

### Phase 2 — open the Compute 550 case
- Sheet-metal enclosure; screws likely under/at the rack ears and rear lip.
- Photograph EVERYTHING before/after each step.

### Phase 3 — board survey (not yet performed)
- Photograph SoC, storage, power circuitry, and wireless module markings.
- Identify possible debug headers from board evidence and measurements.
- Determine signal voltage and pinout before connecting any adapter; neither
  the pinout, voltage, nor baud rate has been established on this board.
- Determine whether a supported diagnostic console or storage backup exists.

### Phase 4 — owner-controlled diagnostics (research goal)
Boot-console access, storage reads, and secure-boot behavior are unverified.
Do not treat generic U-Boot commands or another Lexmark model's pinout as a
working procedure for this device. Prefer documented, reversible inspection
and vendor-assisted backups before considering invasive extraction.

## Open items
- [ ] FCC ID from device label → pull internal photos filing
- [ ] Confirm SoC part number from board photos
- [ ] Locate UART header on actual board
