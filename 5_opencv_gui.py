# Microscope viewer app
# This combines all the stuff I learned from my first 4 test scripts:
#   1_camera_test.py
#   2_zoom_pan.py
#   3_fps_and_capture_mode.py
#   4_resolution_probe.py
#
# Controls:
#   q = quit
#   + = zoom in
#   - = zoom out
#   0 = reset zoom/pan back to normal
#   w/a/s/d = move around when zoomed in
#   1 = low res (800x600, faster, about 28 fps)
#   2 = medium res (1280x960, about 24 fps)
#   3 = high res (2048x1536, slower, about 14 fps)
#   p = take a picture and save it
#
# Note: when you press 1/2/3 it takes a second to switch because the
# camera has to disconnect and reconnect at the new resolution. I put a
# "Switching..." message on screen so it doesn't look frozen while that
# happens.

import cv2
import numpy as np
import os
import time
from datetime import datetime

# where to save snapshots
folder_path = os.path.dirname(os.path.abspath(__file__))
save_folder = os.path.join(folder_path, "img")
if not os.path.exists(save_folder):
    os.makedirs(save_folder)

# which camera to use, change this number if it opens the wrong camera
camera_index = 1

# how much to zoom in/out each time you press + or -
zoom_min = 1.0
zoom_max = 8.0
zoom_step = 0.5

# how far to move when panning with wasd
pan_step = 0.05

# the window will always be this wide so it doesn't change size when
# you switch resolutions
window_width = 800

# text settings for writing on screen
font = cv2.FONT_HERSHEY_SIMPLEX
text_color = (0, 255, 0)
text_size = 0.55
text_thickness = 1
line_gap = 22  # space between lines of text


def resize_to_width(img, width):
    # makes the image exactly "width" pixels wide and keeps it from
    # looking stretched
    h, w = img.shape[:2]
    scale = width / w
    new_w = width
    new_h = int(h * scale)
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


def put_text_top_left(img, text):
    # draws a black box behind the text so you can read it no matter
    # what's behind it
    (text_w, text_h), _ = cv2.getTextSize(text, font, text_size, text_thickness)
    x = 10
    y = 10 + text_h
    cv2.rectangle(img, (x - 4, y - text_h - 4), (x + text_w + 4, y + 4), (0, 0, 0), -1)
    cv2.putText(img, text, (x, y), font, text_size, text_color, text_thickness, cv2.LINE_AA)


def put_text_bottom_left(img, text):
    h, w = img.shape[:2]
    (text_w, text_h), _ = cv2.getTextSize(text, font, text_size, text_thickness)
    x = 10
    y = h - 10
    cv2.rectangle(img, (x - 4, y - text_h - 4), (x + text_w + 4, y + 4), (0, 0, 0), -1)
    cv2.putText(img, text, (x, y), font, text_size, text_color, text_thickness, cv2.LINE_AA)


# this is copied from 2_zoom_pan.py, did not change it
def apply_zoom_pan(frame, zoom, pan_x, pan_y):
    if zoom <= 1.0:
        return frame

    h, w = frame.shape[:2]
    crop_w = w / zoom
    crop_h = h / zoom

    center_x = pan_x * w
    center_y = pan_y * h

    x0 = center_x - crop_w / 2
    y0 = center_y - crop_h / 2

    # don't let it go off the edge of the image
    if x0 < 0:
        x0 = 0
    if y0 < 0:
        y0 = 0
    if x0 > w - crop_w:
        x0 = w - crop_w
    if y0 > h - crop_h:
        y0 = h - crop_h

    x0 = int(x0)
    y0 = int(y0)
    x1 = int(x0 + crop_w)
    y1 = int(y0 + crop_h)

    cropped = frame[y0:y1, x0:x1]
    resized_back = cv2.resize(cropped, (w, h))
    return resized_back


def open_camera(width, height):
    # I have to fully close and reopen the camera to change resolution,
    # because just calling cap.set() on a running camera crashes on my
    # setup (something to do with the MSMF backend). Closing and
    # reopening fresh is slower but it doesn't crash.
    new_cap = cv2.VideoCapture(camera_index)
    new_cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    new_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return new_cap


def show_switching_screen(width, height):
    # show something right away so the screen doesn't look stuck while
    # the camera reconnects
    blank = np.zeros((480, window_width, 3), dtype="uint8")
    msg = "Switching to " + str(width) + "x" + str(height) + "..."
    (text_w, text_h), _ = cv2.getTextSize(msg, font, 1.0, 2)
    x = (window_width - text_w) // 2
    y = (480 + text_h) // 2
    cv2.putText(blank, msg, (x, y), font, 1.0, text_color, 2, cv2.LINE_AA)
    cv2.imshow("Microscope Viewer", blank)
    cv2.waitKey(1)


# start on resolution 2 (medium / "Balanced")
res_choice = 2
res_width = 1280
res_height = 960
res_name = "Balanced"

cap = open_camera(res_width, res_height)

if not cap.isOpened():
    print("Could not open the camera. Check the USB cable and make sure")
    print("no other program is using the camera already.")
    exit()

# variables that change while the program runs
zoom = zoom_min
pan_x = 0.5
pan_y = 0.5  # 0.5 and 0.5 means centered

frame_count = 0
last_fps_time = time.time()
fps = 0.0

print("Controls: q=quit +/-=zoom 0=reset wasd=pan 1/2/3=resolution p=snapshot")
print("Snapshots will be saved in:", save_folder)

while True:
    success, frame = cap.read()
    if not success:
        # sometimes a frame just doesn't come through, skip it and
        # try the next one
        continue

    # count frames per second
    frame_count = frame_count + 1
    now = time.time()
    if now - last_fps_time >= 1.0:
        fps = frame_count / (now - last_fps_time)
        frame_count = 0
        last_fps_time = now

    # do the zoom/pan on the full size image first
    view = apply_zoom_pan(frame, zoom, pan_x, pan_y)

    # save snapshots use "view" before resizing, but here we make a
    # smaller copy called "displayed" just for showing on screen, so
    # snapshots stay full quality no matter what size the window is
    displayed = resize_to_width(view, window_width)

    status_text = "%.1f fps   %dx%d (%s)   zoom %.1fx" % (fps, res_width, res_height, res_name, zoom)
    put_text_top_left(displayed, status_text)
    put_text_bottom_left(displayed, "q quit | +/- zoom | 0 reset | wasd pan | 1/2/3 resolution | p snapshot")

    cv2.imshow("Microscope Viewer", displayed)

    key = cv2.waitKey(1) & 0xFF

    if key == ord('q'):
        break

    elif key == ord('+') or key == ord('='):
        zoom = zoom + zoom_step
        if zoom > zoom_max:
            zoom = zoom_max

    elif key == ord('-'):
        zoom = zoom - zoom_step
        if zoom < zoom_min:
            zoom = zoom_min

    elif key == ord('0'):
        zoom = zoom_min
        pan_x = 0.5
        pan_y = 0.5

    elif key == ord('w'):
        pan_y = pan_y - pan_step
        if pan_y < 0.0:
            pan_y = 0.0

    elif key == ord('s'):
        pan_y = pan_y + pan_step
        if pan_y > 1.0:
            pan_y = 1.0

    elif key == ord('a'):
        pan_x = pan_x - pan_step
        if pan_x < 0.0:
            pan_x = 0.0

    elif key == ord('d'):
        pan_x = pan_x + pan_step
        if pan_x > 1.0:
            pan_x = 1.0

    elif key == ord('1') and res_choice != 1:
        res_choice = 1
        res_width = 800
        res_height = 600
        res_name = "Fast"
        show_switching_screen(res_width, res_height)
        cap.release()
        cap = open_camera(res_width, res_height)
        frame_count = 0
        last_fps_time = time.time()

    elif key == ord('2') and res_choice != 2:
        res_choice = 2
        res_width = 1280
        res_height = 960
        res_name = "Balanced"
        show_switching_screen(res_width, res_height)
        cap.release()
        cap = open_camera(res_width, res_height)
        frame_count = 0
        last_fps_time = time.time()

    elif key == ord('3') and res_choice != 3:
        res_choice = 3
        res_width = 2048
        res_height = 1536
        res_name = "Max detail"
        show_switching_screen(res_width, res_height)
        cap.release()
        cap = open_camera(res_width, res_height)
        frame_count = 0
        last_fps_time = time.time()

    elif key == ord('p'):
        # save "frame" (the original, before zoom/pan) not "view",
        # because zooming in digitally doesn't add any real detail, it
        # just crops and stretches. Saving the original keeps all the
        # real pixels so you can crop into it later in an editor with
        # no quality loss.
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = "snapshot_" + now_str + ".png"
        full_path = os.path.join(save_folder, filename)
        cv2.imwrite(full_path, frame)
        print("Saved snapshot (full resolution " + str(res_width) + "x" + str(res_height) + "):", full_path)

cap.release()
cv2.destroyAllWindows()