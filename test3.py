"""
inspect_usb_descriptors.py

Goal: find out if the microscope's USB descriptors advertise a UVC
"still image capture" capability that's separate from the video streaming
modes OpenCV/MSMF found (which topped out at 2048x1536).

This does NOT touch video streaming at all -- it just reads the device's
descriptor tables, the same data Windows itself reads when it first
enumerates the device. Nothing here can damage the camera; worst case is
a permissions error if Windows already has it locked.

Requires: pip install pyusb
Also requires libusb's Windows driver backend. If pyusb can't find a
backend, see the NOTE at the bottom of this file's output when it fails.

What we're looking for in the output:
  - VIDEO_CONTROL_INTERFACE / VIDEO_STREAMING_INTERFACE class descriptors
  - A "VS_STILL_IMAGE_FRAME" descriptor type (0x03 in the UVC spec) on any
    streaming interface -- this is the formal UVC marker for a dedicated
    still-capture format, separate from regular video frame descriptors
    (which show up as VS_FRAME_UNCOMPRESSED / VS_FRAME_MJPEG, type 0x05/0x07)
  - If we see VS_STILL_IMAGE_FRAME at 2592x1944 (or close), that's a real,
    standards-based still mode we can likely trigger generically.
  - If we see NO still-image frame descriptor anywhere, the 5MP capture is
    either done via a fully vendor-proprietary control (not exposed via
    standard UVC) or is software-side upscaling -- in which case the next
    step is USB packet sniffing of Celestron's own app, not this.
"""

import usb.core
import usb.util
import usb.backend.libusb1
import traceback

# --- Explicit backend loading -------------------------------------------
# get_backend() wraps its real loading steps in "except Exception: log and
# return None". Trying to surface that via logging.basicConfig() didn't
# work (Python 3.14 / some other handler already configured logging, so
# basicConfig() became a silent no-op -- this is documented behavior when
# a handler already exists on the root logger).
#
# Instead of fighting logging config, we bypass it entirely: call the same
# three internal steps get_backend() calls, ourselves, with NO try/except
# at all -- so any real failure prints a full normal Python traceback
# straight to the console, impossible to swallow.
_LIBUSB_DLL_PATH = r"C:\Users\intis\Downloads\Celestron_uScope_GUI\libusb-1.0.dll"

print("Step A: _load_library() ...")
_lib = usb.backend.libusb1._load_library(find_library=lambda x: _LIBUSB_DLL_PATH)
print(f"  OK, got: {_lib}")

print("Step B: _setup_prototypes(lib) ...")
usb.backend.libusb1._setup_prototypes(_lib)
print("  OK")

print("Step C: _LibUSB(lib) ...")
_backend = usb.backend.libusb1._LibUSB(_lib)
print(f"  OK, backend object: {_backend}")

print("\nBackend loaded successfully -- no exception was hidden this time.\n")

# Celestron microscope USB identifiers -- if this script can't find the
# device, run list_all_usb_devices() below first and update these.
VENDOR_ID = 0x0c45   # Sonix Technology Co. -- confirmed via Device Manager
PRODUCT_ID = 0x6353   # confirmed via Device Manager (VID_0C45&PID_6353)

# UVC descriptor type constants (from the USB Video Class 1.1/1.5 spec)
CS_INTERFACE = 0x24
VC_HEADER = 0x01
VS_INPUT_HEADER = 0x01
VS_FORMAT_UNCOMPRESSED = 0x04
VS_FRAME_UNCOMPRESSED = 0x05
VS_FORMAT_MJPEG = 0x06
VS_FRAME_MJPEG = 0x07
VS_STILL_IMAGE_FRAME = 0x03  # <-- the one we actually care about


def list_all_usb_devices():
    """Print every USB device so you can identify the microscope's
    VID:PID if VENDOR_ID/PRODUCT_ID above aren't already known."""
    print("All connected USB devices:")
    print("-" * 70)
    for dev in usb.core.find(find_all=True, backend=_backend):
        try:
            mfg = usb.util.get_string(dev, dev.iManufacturer) if dev.iManufacturer else "?"
            prod = usb.util.get_string(dev, dev.iProduct) if dev.iProduct else "?"
        except Exception:
            mfg, prod = "?", "?"
        print(f"  VID=0x{dev.idVendor:04x}  PID=0x{dev.idProduct:04x}  "
              f"Manufacturer={mfg}  Product={prod}")
    print("-" * 70)
    print("Find the line that looks like the Celestron scope (often")
    print("Manufacturer/Product mention the chipset vendor, not 'Celestron'")
    print("itself -- many of these use generic Sonix/Etron/etc. UVC chips).")
    print("Then set VENDOR_ID / PRODUCT_ID at the top of this script and")
    print("re-run.")


def parse_class_specific_descriptors(extra_bytes):
    """Walk a raw extra-descriptor blob from a USB interface and report
    every UVC class-specific (CS_INTERFACE) descriptor found, decoding
    the ones relevant to still-image capture."""
    i = 0
    found_still_frame = False
    n = len(extra_bytes)

    while i < n:
        if i + 1 >= n:
            break
        length = extra_bytes[i]
        if length == 0:
            break
        desc_type = extra_bytes[i + 1]

        if desc_type == CS_INTERFACE and length >= 3:
            subtype = extra_bytes[i + 2]

            if subtype == VS_STILL_IMAGE_FRAME:
                found_still_frame = True
                print("  >>> FOUND VS_STILL_IMAGE_FRAME descriptor! <<<")
                print(f"      raw bytes: {extra_bytes[i:i+length].hex()}")
                # Per UVC spec layout for this descriptor:
                #   byte 3 = bFormatIndex, byte 4 = bEndpointAddress,
                #   byte 5 = bNumImageSizePatterns, then pairs of
                #   (wWidth, wHeight) for each pattern.
                if length >= 6:
                    num_patterns = extra_bytes[i + 5]
                    print(f"      advertises {num_patterns} still-image size(s):")
                    offset = i + 6
                    for p in range(num_patterns):
                        if offset + 4 <= n:
                            w = extra_bytes[offset] | (extra_bytes[offset + 1] << 8)
                            h = extra_bytes[offset + 2] | (extra_bytes[offset + 3] << 8)
                            mp = (w * h) / 1_000_000
                            print(f"        size {p}: {w}x{h}  ({mp:.2f} MP)")
                            offset += 4

            elif subtype == VS_FRAME_UNCOMPRESSED or subtype == VS_FRAME_MJPEG:
                kind = "UNCOMPRESSED" if subtype == VS_FRAME_UNCOMPRESSED else "MJPEG"
                if length >= 9:
                    w = extra_bytes[i + 5] | (extra_bytes[i + 6] << 8)
                    h = extra_bytes[i + 7] | (extra_bytes[i + 8] << 8)
                    print(f"  (regular video frame, {kind}: {w}x{h})")

        i += length

    return found_still_frame


def inspect_device(vendor_id, product_id):
    dev = usb.core.find(idVendor=vendor_id, idProduct=product_id, backend=_backend)
    if dev is None:
        print(f"Could not find device VID=0x{vendor_id:04x} PID=0x{product_id:04x}")
        print("Is it plugged in? Is Celestron's own software closed?")
        return

    print(f"Found device: VID=0x{vendor_id:04x} PID=0x{product_id:04x}")
    print(f"  {usb.util.get_string(dev, dev.iManufacturer, 1000) if dev.iManufacturer else ''} "
          f"{usb.util.get_string(dev, dev.iProduct, 1000) if dev.iProduct else ''}")
    print()

    found_any_still_frame = False

    for cfg in dev:
        for intf in cfg:
            # UVC streaming interfaces are class 0x0E (Video), subclass 0x02
            if intf.bInterfaceClass == 0x0E:
                print(f"Interface {intf.bInterfaceNumber}, alt setting "
                      f"{intf.bAlternateSetting}, subclass=0x{intf.bInterfaceSubClass:02x}")
                extra = bytes(intf.extra_descriptors) if hasattr(intf, "extra_descriptors") else b""
                if not extra:
                    # pyusb sometimes exposes this differently depending on
                    # backend; fall back to the raw descriptor walk if needed.
                    print("  (no extra descriptor bytes exposed by this backend/intf)")
                    continue
                found = parse_class_specific_descriptors(extra)
                found_any_still_frame = found_any_still_frame or found

    print()
    print("=" * 70)
    if found_any_still_frame:
        print("RESULT: Device DOES advertise a standards-based UVC still-image")
        print("capture mode. This means we can likely trigger a real 5MP still")
        print("using a standard UVC still-probe/still-commit control sequence,")
        print("without needing to reverse-engineer Celestron's own software.")
        print("Next step: write a still-capture trigger script.")
    else:
        print("RESULT: No VS_STILL_IMAGE_FRAME descriptor found on any")
        print("streaming interface. This means the 5MP capture (if it is a")
        print("real optical capture and not just software upscaling) is")
        print("almost certainly done via a vendor-proprietary USB control")
        print("transfer that only Celestron's own MicroCapture Pro knows.")
        print("Next step would be USB packet sniffing (Wireshark + USBPcap)")
        print("while pressing 'capture' in Celestron's own app, to find that")
        print("specific control sequence -- a bigger undertaking, and one")
        print("that's worth pausing on before committing to it.")


if __name__ == "__main__":
    if VENDOR_ID is None or PRODUCT_ID is None:
        print("VENDOR_ID/PRODUCT_ID not set yet -- listing all USB devices")
        print("so you can identify the microscope first.\n")
        list_all_usb_devices()
    else:
        inspect_device(VENDOR_ID, PRODUCT_ID)