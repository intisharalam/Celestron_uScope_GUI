"""
This merges everything from scripts 1-4 into one working app:
  1_camera_test.py        -> opening the camera
  2_zoom_pan.py            -> apply_zoom_pan() function (unchanged)
  3_fps_and_capture_mode.py -> measuring real FPS
  4_resolution_probe.py    -> the 3 real resolution tiers this camera supports

Controls (also drawn on-screen, bottom-left of the window):
  q        quit
  +/-      zoom in/out
  0        reset zoom and pan
  w/a/s/d  pan around while zoomed in
  1        resolution: Fast    (800x600,   ~28 fps)
  2        resolution: Balanced (1280x960,  ~24 fps)
  3        resolution: Max detail (2048x1536, ~14 fps)
  p        save a snapshot (PNG) of exactly what's on screen

NOTE on resolution switching speed: pressing 1/2/3 closes and reopens the
camera connection (see open_camera_at() below for why). That reconnect
takes a real moment -- there's no way to make the USB renegotiation itself
instant -- but we show a "Switching..." message immediately so it's clear
the app hasn't frozen while that happens.
"""

import cv2
import numpy as np
import os
import time
from datetime import datetime

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_DIR = os.path.join(SCRIPT_DIR, "img")
os.makedirs(SAVE_DIR, exist_ok=True)

# The 3 real resolution tiers found by 4_resolution_probe.py.
# Key = the number key that selects it.
#
# NOTE: this camera does NOT keep the same field of view across tiers.
# Higher resolutions read out a smaller, more central region of the sensor,
# so "Max detail" looks more zoomed-in than "Fast"/"Balanced" even at
# zoom=1.0x. This is a hardware/firmware behavior, not a bug -- there's
# nothing wrong with apply_zoom_pan() or resize_to_width() below. If you
# want the same framing across tiers, physically move the scope further
# from the subject when using "Max detail".
RESOLUTIONS = {
    ord('1'): ("Fast",       800, 600),
    ord('2'): ("Balanced",   1280, 960),
    ord('3'): ("Max detail", 2048, 1536),
}

ZOOM_MIN = 1.0
ZOOM_MAX = 8.0
ZOOM_STEP = 0.5
PAN_STEP = 0.05

# The on-screen window is always resized to exactly this width, no matter
# what capture resolution is selected -- this keeps every tier the same
# window size so switching tiers doesn't make the window visibly grow or
# shrink. This only affects what's DISPLAYED -- snapshots are still saved
# at the full captured resolution (see take snapshot below, which saves
# `view`, not the resized `displayed`).
DISPLAY_WIDTH = 1280  # comfortably fits on a 1920x1080 screen with room
                       # for the taskbar/other windows

# Text overlay appearance
FONT = cv2.FONT_HERSHEY_SIMPLEX
TEXT_COLOR = (0, 255, 0)
TEXT_SCALE = 0.55
TEXT_THICKNESS = 1
LINE_HEIGHT = 22  # vertical spacing between stacked lines of text

CONTROLS_TEXT = [
    "q quit | +/- zoom | 0 reset | wasd pan | 1/2/3 resolution | p snapshot",
]


def resize_to_width(frame, width):
    """Scale a frame to exactly `width` pixels wide, keeping aspect ratio.
    Unlike a 'max width' cap, this ALWAYS resizes -- so every tier ends up
    the same on-screen size, instead of smaller captures just staying small."""
    h, w = frame.shape[:2]
    scale = width / w
    new_size = (width, int(h * scale))
    return cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)


def draw_text_lines(frame, lines, anchor="top-left"):
    """Draw a stack of text lines onto a frame, anchored to a screen corner.

    Each line gets a dark semi-transparent backing rectangle behind it so
    the text stays readable regardless of what's in the live image behind
    it (plain green text on a plain bright background would otherwise be
    hard to read).
    """
    h, w = frame.shape[:2]
    margin = 10

    for i, line in enumerate(lines):
        (text_w, text_h), _ = cv2.getTextSize(line, FONT, TEXT_SCALE, TEXT_THICKNESS)

        if anchor == "top-left":
            x = margin
            y = margin + text_h + i * LINE_HEIGHT
        elif anchor == "bottom-left":
            x = margin
            y = h - margin - (len(lines) - 1 - i) * LINE_HEIGHT
        else:
            raise ValueError(f"Unknown anchor: {anchor}")

        # backing rectangle, slightly larger than the text itself
        cv2.rectangle(frame,
                      (x - 4, y - text_h - 4),
                      (x + text_w + 4, y + 4),
                      (0, 0, 0), thickness=-1)

        cv2.putText(frame, line, (x, y), FONT, TEXT_SCALE,
                    TEXT_COLOR, TEXT_THICKNESS, cv2.LINE_AA)


# ---------------------------------------------------------------------------
# Zoom / pan -- straight from 2_zoom_pan.py, unchanged
# ---------------------------------------------------------------------------

def apply_zoom_pan(frame, zoom, pan_x, pan_y):
    """Crop the frame around (pan_x, pan_y) at the given zoom level, then
    resize back up to full size so nothing downstream needs to know about zoom."""
    if zoom <= 1.0:
        return frame

    h, w = frame.shape[:2]
    crop_w = w / zoom
    crop_h = h / zoom

    cx = pan_x * w
    cy = pan_y * h

    x0 = int(max(0, min(w - crop_w, cx - crop_w / 2)))
    y0 = int(max(0, min(h - crop_h, cy - crop_h / 2)))
    x1 = int(x0 + crop_w)
    y1 = int(y0 + crop_h)

    cropped = frame[y0:y1, x0:x1]
    return cv2.resize(cropped, (w, h))


# ---------------------------------------------------------------------------
# Camera setup
# ---------------------------------------------------------------------------

CAMERA_INDEX = 1  # change this if your microscope shows up at a different index

def open_camera_at(res_key):
    """(Re)open the camera fresh at the given resolution.

    Why reopen instead of just calling cap.set() on the running camera?
    On this camera + the MSMF backend, changing resolution on a live
    stream corrupts the next frame and crashes. Releasing the camera and
    opening it again at the new resolution avoids that entirely -- it's
    a bit slower (a short reconnect pause) but reliable.
    """
    _, width, height = RESOLUTIONS[res_key]
    new_cap = cv2.VideoCapture(CAMERA_INDEX)
    new_cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    new_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return new_cap, width, height


def show_switching_message(width, height):
    """Display an immediate placeholder frame so the app doesn't look
    frozen during the reconnect pause when changing resolution."""
    placeholder = np.zeros((480, DISPLAY_WIDTH, 3), dtype="uint8")
    msg = f"Switching to {width}x{height}..."
    (text_w, text_h), _ = cv2.getTextSize(msg, FONT, 1.0, 2)
    x = (DISPLAY_WIDTH - text_w) // 2
    y = (480 + text_h) // 2
    cv2.putText(placeholder, msg, (x, y), FONT, 1.0, TEXT_COLOR, 2, cv2.LINE_AA)
    cv2.imshow("Microscope Viewer", placeholder)
    cv2.waitKey(1)  # force the window to actually repaint right now


# Start on the "Balanced" tier
current_res_key = ord('2')
cap, w, h = open_camera_at(current_res_key)

if not cap.isOpened():
    print("Could not open the camera. Check the USB connection and that")
    print("no other program (e.g. Celestron's own software) is using it.")
    raise SystemExit(1)

# ---------------------------------------------------------------------------
# State that the keyboard controls below will change
# ---------------------------------------------------------------------------

zoom = ZOOM_MIN
pan_x, pan_y = 0.5, 0.5  # 0.5, 0.5 = centered

# FPS is measured once per second, at the camera-read loop (not the display
# loop), same approach as 3_fps_and_capture_mode.py.
frame_count = 0
fps_clock = time.time()
measured_fps = 0.0

print("Controls: q=quit  +/-=zoom  0=reset  wasd=pan  1/2/3=resolution  p=snapshot")
print(f"Saving snapshots to: {SAVE_DIR}")

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

while True:
    ok, frame = cap.read()
    if not ok:
        # A dropped frame is not fatal -- just skip it and try again.
        continue

    # --- measure FPS ---
    frame_count += 1
    now = time.time()
    if now - fps_clock >= 1.0:
        measured_fps = frame_count / (now - fps_clock)
        frame_count = 0
        fps_clock = now

    # --- apply zoom/pan (at full captured resolution) ---
    view = apply_zoom_pan(frame, zoom, pan_x, pan_y)

    # `view` (full resolution) is what gets saved on snapshot -- this
    # happens BEFORE any text is drawn, so overlays never end up baked
    # into saved images.
    # `displayed` (scaled to a fixed width) is only what's drawn in the window.
    displayed = resize_to_width(view, DISPLAY_WIDTH)

    res_name, _, _ = RESOLUTIONS[current_res_key]
    status_line = f"{measured_fps:4.1f} fps   {w}x{h} ({res_name})   zoom {zoom:.1f}x"
    draw_text_lines(displayed, [status_line], anchor="top-left")
    draw_text_lines(displayed, CONTROLS_TEXT, anchor="bottom-left")

    cv2.imshow("Microscope Viewer", displayed)

    # --- handle keyboard input ---
    key = cv2.waitKey(1) & 0xFF

    if key == ord('q'):
        break

    elif key in (ord('+'), ord('=')):
        zoom = min(ZOOM_MAX, zoom + ZOOM_STEP)

    elif key == ord('-'):
        zoom = max(ZOOM_MIN, zoom - ZOOM_STEP)

    elif key == ord('0'):
        zoom = ZOOM_MIN
        pan_x, pan_y = 0.5, 0.5

    elif key == ord('w'):
        pan_y = max(0.0, pan_y - PAN_STEP)

    elif key == ord('s'):
        pan_y = min(1.0, pan_y + PAN_STEP)

    elif key == ord('a'):
        pan_x = max(0.0, pan_x - PAN_STEP)

    elif key == ord('d'):
        pan_x = min(1.0, pan_x + PAN_STEP)

    elif key in RESOLUTIONS and key != current_res_key:
        current_res_key = key
        _, new_w, new_h = RESOLUTIONS[current_res_key]
        show_switching_message(new_w, new_h)  # immediate feedback, before the slow part

        cap.release()                       # close the old stream first
        cap, w, h = open_camera_at(current_res_key)  # then open fresh at new size
        # Don't let FPS numbers from the old resolution bleed into the new one
        frame_count = 0
        fps_clock = time.time()

    elif key == ord('p'):
        # Save `frame` (raw from the sensor) rather than `view` (after
        # digital zoom/pan). Digital zoom only crops + upscales -- it adds
        # no real detail, so baking it into the saved file would just
        # throw away resolution permanently. Saving the raw frame instead
        # keeps every real pixel the sensor captured; you can always crop
        # or zoom into the saved PNG afterwards with NO quality loss
        # compared to baking the same zoom in now.
        filename = datetime.now().strftime("snapshot_%Y%m%d_%H%M%S.png")
        path = os.path.join(SAVE_DIR, filename)
        cv2.imwrite(path, frame)
        print(f"Saved (full sensor resolution {w}x{h}):", path)

cap.release()
cv2.destroyAllWindows()