#!/usr/bin/env python3
"""Probe the Roca Sifter (Lexmark Optra Compute 550) over USB from Linux.

Stages:
  desc  - dump full descriptors (safe, read-only)
  listen-ff - claim the vendor-specific interface (ff/ff/ff) and print
              anything the device sends (passive read loop)
  listen-hid- read HID reports (button presses etc.)
  send  - send raw bytes to an endpoint: send <iface> <ep> <hexbytes>

Usage:
  sudo ./usb-probe.py desc
  sudo ./usb-probe.py listen-ff [--seconds 30]
  sudo ./usb-probe.py send ff 0x01 1b 45 45   # example ESC/EE to printer ep

Requires: pip install pyusb (and libusb present).
Device: VID 0x043D (Lexmark), PID 0x0122, serial "1235".
"""
import argparse
import sys
import time

import usb.core
import usb.util

VID, PID = 0x043D, 0x0122


def find():
    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        sys.exit("Sifter not found (VID %04x PID %04x). Is it plugged in?" % (VID, PID))
    return dev


def detach_kernel(dev):
    if dev.is_kernel_driver_active(0):
        try:
            dev.detach_kernel_driver(0)
        except usb.core.USBError:
            pass


def show_desc(dev):
    print(dev)
    print("serial:", usb.util.get_string(dev, dev.iSerialNumber))
    print("product:", usb.util.get_string(dev, dev.iProduct))
    for cfg in dev:
        print("\nConfiguration", cfg.bConfigurationValue)
        for iface in cfg:
            print("  Interface %d class=%02x sub=%02x proto=%02x (%s)" % (
                iface.bInterfaceNumber, iface.bInterfaceClass,
                iface.bInterfaceSubClass, iface.bInterfaceProtocol,
                usb.util.get_string(dev, iface.iInterface)))
            for ep in iface:
                print("    EP 0x%02x attr=%02x maxpkt=%d interval=%d" % (
                    ep.bEndpointAddress, ep.bmAttributes,
                    ep.wMaxPacketSize, ep.bInterval))


def listen(dev, iface_num, seconds):
    cfg = dev.get_active_configuration()
    iface = usb.util.find_descriptor(cfg, bInterfaceNumber=iface_num)
    if iface is None:
        sys.exit("interface %d not found" % iface_num)
    had_kernel = dev.is_kernel_driver_active(iface_num)
    if had_kernel:
        dev.detach_kernel_driver(iface_num)
    usb.util.claim_interface(dev, iface_num)
    eps = [ep for ep in iface if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN]
    if not eps:
        sys.exit("no IN endpoint on interface %d" % iface_num)
    ep = eps[0]
    print("listening on iface %d EP 0x%02x for %ds..." % (iface_num, ep.bEndpointAddress, seconds))
    end = time.time() + seconds
    n = 0
    while time.time() < end:
        try:
            data = dev.read(ep.bEndpointAddress, ep.wMaxPacketSize, timeout=1000)
            n += 1
            print("[%6.2f] %d bytes: %s" % (time.time() % 1000, len(data), data.hex()))
        except usb.core.USBError as e:
            if e.errno != 110:  # timeout
                raise
    print("%d transfers" % n)
    usb.util.release_interface(dev, iface_num)
    if had_kernel:
        try:
            dev.attach_kernel_driver(iface_num)
        except usb.core.USBError:
            pass


def send(dev, iface_num, ep_addr, payload):
    had_kernel = dev.is_kernel_driver_active(iface_num)
    if had_kernel:
        dev.detach_kernel_driver(iface_num)
    usb.util.claim_interface(dev, iface_num)
    dev.write(ep_addr, payload, timeout=3000)
    print("sent %d bytes to 0x%02x" % (len(payload), ep_addr))
    usb.util.release_interface(dev, iface_num)
    if had_kernel:
        try:
            dev.attach_kernel_driver(iface_num)
        except usb.core.USBError:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["desc", "listen-ff", "listen-hid", "send"])
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("extra", nargs="*", help="send: <iface> <ep-hex> <hexbytes...>")
    args = ap.parse_args()
    dev = find()
    if args.cmd == "desc":
        show_desc(dev)
    elif args.cmd == "listen-ff":
        cfg = dev.get_active_configuration()
        ff = [i.bInterfaceNumber for i in cfg if i.bInterfaceClass == 0xFF]
        if not ff:
            sys.exit("no vendor-specific interface found")
        listen(dev, ff[0], args.seconds)
    elif args.cmd == "listen-hid":
        cfg = dev.get_active_configuration()
        hid = [i.bInterfaceNumber for i in cfg if i.bInterfaceClass == 3]
        if not hid:
            sys.exit("no HID interface found")
        listen(dev, hid[0], args.seconds)
    elif args.cmd == "send":
        iface_num = int(args.extra[0], 0)
        ep = int(args.extra[1], 16)
        payload = bytes(int(b, 16) for b in args.extra[2:])
        send(dev, iface_num, ep, payload)


if __name__ == "__main__":
    main()
