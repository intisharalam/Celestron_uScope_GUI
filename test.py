"""
7_max_resolution_test.py -- How many megapixels can we actually get?

This goes wider than 4_resolution_probe.py: it tries a long list of
resolutions (including some bigger than the camera's spec sheet claims,
just to see what the driver does with an unreasonable request) and reports
the actual resolution + megapixel count the camera settles on for each.

Remember (from earlier testing): this only probes the LIVE VIDEO stream.
The sensor's separate 5MP "still capture" pin is a different, currently
unreachable path (see notes from the winsdk/Media Foundation investigation).
This script answers "what's the most detail OpenCV can get us", not
"what's the sensor's absolute maximum capability".

NOTE: some requested resolutions make this camera's driver (on the MSMF
backend) return a corrupt/invalid frame instead of cleanly failing -- this
crashes cv2.read() with a low-level OpenCV assertion error if unguarded
(we hit exactly this in 4_resolution_probe.py too). The try/except below
catches that and just skips the bad resolution, the same fix used there.
NOTE: this camera's MSMF backend cannot tolerate changing resolution on
an already-running stream -- calling cap.set() repeatedly on one open
cap object corrupts the very next frame, even for resolutions that work
perfectly fine on their own (we proved this with 800x600, 1280x960, and
2048x1536, which all work in 5_combine.py but failed here in an earlier
version of this script that reused one cap object). The fix, same one
used in 5_combine.py's open_camera_at(): release and reopen the camera
fresh for every resolution, instead of reconfiguring a live one.
"""

import cv2

CAMERA_INDEX = 1  # match whatever worked in 5_combine.py

# A wide sweep: includes the tiers we already know about, the higher
# "still capture" sizes from the manual spec sheet (just in case the
# video pin secretly supports them too), and some intentionally
# oversized requests to see what the driver clamps down to.
candidates = [
    (320, 240),
    (640, 480),
    (800, 600),
    (1024, 768),
    (1280, 720),
    (1280, 960),
    (1280, 1024),
    (1600, 1200),
    (1920, 1080),
    (2048, 1536),
    (2320, 1744),
    (2592, 1944),   # the "5MP still" size from the manual -- almost
                     # certainly won't work over video, but worth trying
    (3264, 2448),
    (4000, 3000),    # deliberately oversized, to see the driver clamp
]


def megapixels(w, h):
    return (w * h) / 1_000_000


def try_resolution(req_w, req_h):
    """Open a FRESH camera connection for this one resolution, grab a
    frame, then close it again. Returns (actual_w, actual_h) on success,
    or None on failure. Opening fresh each time avoids the live-resize
    crash described above."""
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        return None

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, req_w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, req_h)

    try:
        ok, frame = cap.read()
    except cv2.error:
        ok = False
        frame = None

    cap.release()

    if not ok or frame is None:
        return None

    actual_h, actual_w = frame.shape[:2]  # read the REAL size from the
                                            # frame itself, not just from
                                            # cap.get(), to be extra sure
    return actual_w, actual_h


results = {}  # (actual_w, actual_h) -> megapixels, de-duplicated automatically

for req_w, req_h in candidates:
    actual = try_resolution(req_w, req_h)

    if actual is None:
        print(f"  requested {req_w:5d}x{req_h:<5d} -> failed, skipping")
        continue

    actual_w, actual_h = actual
    mp = megapixels(actual_w, actual_h)

    print(f"  requested {req_w:5d}x{req_h:<5d} -> got {actual_w}x{actual_h}  "
          f"({mp:.2f} MP)")

    results[(actual_w, actual_h)] = mp

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

if not results:
    print("\nNo resolutions worked at all -- check the camera connection.")
else:
    best_w, best_h = max(results, key=lambda wh: results[wh])
    best_mp = results[(best_w, best_h)]

    print("\nAll distinct resolutions found (smallest to largest):")
    for (w, h), mp in sorted(results.items(), key=lambda item: item[1]):
        print(f"  {w}x{h}  ({mp:.2f} MP)")

    print(f"\nHighest reachable over the live video stream: "
          f"{best_w}x{best_h}  ({best_mp:.2f} MP)")