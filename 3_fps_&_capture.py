"""
This was fully claude, not gonna lie
"""

import cv2
import time

def measure_fps(width, height, fourcc_name, seconds=3):
    cap = cv2.VideoCapture(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if fourcc_name:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc_name))

    # actual negotiated values may differ from what we asked for
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # warm up — first few frames after a settings change are often slow/junk
    for _ in range(5):
        cap.read()

    count = 0
    start = time.time()
    while time.time() - start < seconds:
        ok, _ = cap.read()
        if ok:
            count += 1
    elapsed = time.time() - start

    cap.release()
    fps = count / elapsed
    print(f"{fourcc_name or 'default':6s}  requested {width}x{height}  "
          f"actual {actual_w}x{actual_h}  ->  {fps:.1f} fps")

measure_fps(800, 600, "MJPG")
measure_fps(800, 600, "YUY2")

"""
capture-mode not needed. does nothing.
flat cap of 14fps and otherwise 27 fps.

MJPG    requested 2592x1944  actual 2048x1536  ->  14.0 fps
YUY2    requested 2592x1944  actual 2048x1536  ->  14.3 fps
MJPG    requested 1920x1080  actual 1600x1200  ->  14.2 fps
YUY2    requested 1920x1080  actual 1600x1200  ->  14.0 fps
MJPG    requested 640x480  actual 640x480  ->  27.1 fps
YUY2    requested 640x480  actual 640x480  ->  27.1 fps
"""

"""

"""