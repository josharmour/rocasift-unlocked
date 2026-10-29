# Sifter USB probe — runbook for the Omarchy (Arch) machine

Goal: characterize the Sifter's USB device port (rear USB-B) from Linux,
where we can claim interfaces raw (macOS blocks this via DriverKit).

Known so far (from macOS enumeration, 2026-10-27):

- Device: "Lexmark xxxx", VID `043d`, PID `0122`, serial `1235`,
  USB 2.0 High-Speed, bcdUSB 2.00.
- Composite device, 3 interfaces:
  - HID `(03/00/00)`
  - vendor-specific `(ff/ff/ff)` ← primary RE target
  - USB printer class `(07/01/02)` bidirectional
- No CDC network gadget on fw 3.5.4 — EWS-over-USB (169.254.76.86) is absent.
- Evidence: `device/usb-lexmark-isolated-20261027.txt`,
  `device/usb-ioreg-full-after-replug-20261027.txt`.

## Status (2026-10-27, evening)

- Stages 1–3 DONE; results in `FINDINGS.md` §9b–§9d, captures in
  `device/usb/`.
- Stimulus captures during a live job (~10 cards scanned): **zero
  device-originated USB traffic on any interface** — see §9d. Passive
  listening is exhausted; Stage 4 (driving EP `0x02` OUT) is the next lever.
- Button/HID redo pending: first trial was invalid (usbhid had been detached;
  reattached 18:03). Press buttons again with `listen-hid` or usbmon live.
- Operational pitfalls learned tonight:
  - After `detach_kernel_driver`, ALWAYS `attach_kernel_driver` on release —
    a forgotten reattach silently removes hidraw and invalidates later tests.
  - Redirected python stdout block-buffers: a listener writing to a file
    shows nothing until exit. Use `python3 -u` for live-tailed captures.
  - Never overlap two capture windows — the second `listen-ff` dies with
    `EBUSY` while the first still holds the interface.
  - Host sleep kills captures mid-run (`Errno 112 Host is down` /
    `Errno 5 I/O error` at resume). For long windows inhibit sleep, e.g.
    `systemd-inhibit --what=sleep <cmd>`, or keep the machine awake.

## Setup (once)

```sh
sudo pacman -S libusb python-pyusb   # omarchy/arch package names
# verify device visible:
lsusb | grep -i 043d
```

Copy `tools/usb-probe.py` from this repo to the omarchy machine (or clone it).

## Stage 1 — descriptors (safe, read-only)

```sh
sudo python3 usb-probe.py desc > usb-desc.txt
lsusb -v -d 043d:0122 > usb-lsusb-v.txt
```

Record: endpoint addresses/directions per interface, any class-specific
descriptors on the ff interface, max packet sizes.

## Stage 2 — passive listen on the vendor interface

Run the bus-wide sniffer CONCURRENTLY with the claim listener — usbmon sees
every interface (including kernel-driver-handled HID/printer traffic) without
claiming anything, while the claim listener is the only thing polling the
Scan bulk-IN endpoint:

```sh
sudo modprobe usbmon   # once per boot
sudo ./tools/usbmon-sniff.py --bus 1 --dev 5 --seconds 180 \
    --out device/usb/usb-usbmon-job-$(date +%Y%m%d).txt &
sudo python3 usb-probe.py listen-ff --seconds 180 | tee usb-ff-job.txt
```

`usbmon-sniff.py` auto-detects this kernel's usbmon header size (48 vs 64
bytes — they differ!) and drains via sleep-poll; see its docstring and the
`linux-usb-probing` skill for the two kernel quirks that silently break
naive implementations.

```sh
sudo python3 usb-probe.py listen-ff --seconds 120 | tee usb-ff-idle.txt
```

Then repeat while driving the device, to correlate traffic:

```sh
sudo python3 usb-probe.py listen-ff --seconds 180 | tee usb-ff-job.txt
# during the capture: start a sift job from the EWS (LAN) or press buttons
```

Compare idle vs job captures — differing bytes are the job/control channel.

Also listen to HID while pressing front-panel buttons:

```sh
sudo python3 usb-probe.py listen-hid --seconds 60 | tee usb-hid-buttons.txt
```

## Stage 3 — printer class sanity check

The printer interface may accept standard PCL/ESC jobs. From Linux with CUPS:

```sh
lp -d <queue> /etc/hostname   # or raw: cat file > /dev/usb/lp0
```

If a queue auto-appears, note its URI (`lpstat -v`). A working raw print path
is a candidate job-injection route independent of the cloud/EWS.

## Stage 5 — USB-A host port (Sifter acts as host)

The other rear port is USB-A **host** role: peripherals plug INTO the Sifter
(Optra docs: storage, MarkNet adapters). Cannot be probed from a computer
directly; test by feeding it devices:

1. Plug a FAT32 flash stick into the USB-A port.
2. Check the EWS for new settings keys or endpoints mentioning USB/storage
   (`GET /webservices/settings/<keys>`; compare key list before/after).
3. Run a sift job with the stick inserted; afterwards mount it on a PC and
   inventory anything written (scans, logs, config).
4. Optional: try a USB-Ethernet adapter — if enumerated, the device gains a
   second NIC worth investigating.

Motivation: inherited Lexmark print-stack features often include scan-to-USB;
a working local export route would satisfy the project's owner-control goal
independently of the cloud pipeline.

## Stage 4 — talking to the ff interface (only after Stage 2)

Send only after we've seen real traffic patterns; echo/replay known-good
frames first:

```sh
sudo python3 usb-probe.py send <iface> <ep-hex> <hexbytes...>
```

Rules: never write to EP0 with arbitrary control requests; replay captured
frames before crafting new ones; one change at a time.

## Recording results

Save all captures under `device/usb/` in this repo named
`usb-<what>-<yyyymmdd>.txt`, and summarize findings in `FINDINGS.md`
(mark observations `[O]`, inferences `[I]`, include date + reproduction steps).
Note kernel/distro (`uname -a`) with each capture.
