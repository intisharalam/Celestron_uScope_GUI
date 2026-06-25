"""
6_fov_test.py -- Raw field-of-view comparison across resolution tiers

No zoom, no pan, no resizing, no FPS overlay -- just: open the camera at
each resolution, wait for it to settle, grab one frame, and show it.

This isolates whether the "narrower FOV at higher resolution" effect is
really coming from the sensor/firmware, or from something in our app's
processing (resize_to_fit, apply_zoom_pan, etc).

Keep all 3 windows open and visually compare how much of the subject is
visible in each -- point the microscope at something with clear edges
(a ruler, a coin, a sheet of paper with a printed grid) so it's obvious
whether the framing changes between tiers.

Press any key (with a window focused) to close all windows and exit.
"""

import cv2
import time

CAMERA_INDEX = 1  # match whatever worked in 5_combine.py

RESOLUTIONS = {
    "Fast (800x600)":       (800, 600),
    "Balanced (1280x960)":  (1280, 960),
    "Max detail (2048x1536)": (2048, 1536),
}

SETTLE_SECONDS = 5  # how long to wait after setting resolution before
                     # trusting the frame we grab


def grab_one_still(width, height):
    """Open the camera fresh, request a resolution, wait for it to settle,
    grab exactly one frame, then close the camera again."""
    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    print(f"  Waiting {SETTLE_SECONDS}s for sensor to stabilize...")
    # Keep reading (and discarding) frames while we wait, rather than just
    # time.sleep(), so the camera's internal buffer doesn't fill up with
    # stale frames -- we want the LAST frame read to be a fresh one.
    settle_until = time.time() + SETTLE_SECONDS
    frame = None
    while time.time() < settle_until:
        ok, frame = cap.read()

    # One more read after the settle period, to be the actual "real" frame
    ok, frame = cap.read()

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    cap.release()

    if not ok or frame is None:
        print(f"  Failed to grab a frame at {width}x{height}")
        return None, actual_w, actual_h

    return frame, actual_w, actual_h


# ---------------------------------------------------------------------------
# Capture one still per tier
# ---------------------------------------------------------------------------

captured = {}  # label -> (frame, actual_w, actual_h)

for label, (req_w, req_h) in RESOLUTIONS.items():
    print(f"\nCapturing: {label}  (requested {req_w}x{req_h})")
    frame, actual_w, actual_h = grab_one_still(req_w, req_h)
    captured[label] = (frame, actual_w, actual_h)
    print(f"  Got: {actual_w}x{actual_h}")

# ---------------------------------------------------------------------------
# Show all 3 windows at once
# ---------------------------------------------------------------------------

print("\nShowing all 3 windows. Press any key to close and exit.")

for label, (frame, actual_w, actual_h) in captured.items():
    if frame is None:
        continue
    window_title = f"{label}  [{actual_w}x{actual_h}]"
    cv2.imshow(window_title, frame)

cv2.waitKey(0)
cv2.destroyAllWindows()