# Microscope viewer app
# This is my merged viewer (camera, zoom/pan, fps counter, the 3
# resolutions, snapshot) PLUS a new feature: stacked capture.
#
# What is "stacked capture" (key: k)?
# ------------------------------------
# Single pictures from this camera are noisy/grainy, especially on flat
# areas. The noise is RANDOM each frame, but the actual specimen detail
# is the SAME every frame. So if I take like 16 pictures in a row and
# average them together, the random noise mostly cancels itself out
# (averaging N frames cuts noise by about sqrt(N)) but the real detail
# stays just as strong. So the averaged picture ends up looking cleaner,
# without making anything up - the detail was already there, just hidden
# under noise.
#
# After averaging I also sharpen the image a bit (unsharp mask). I only
# do this AFTER averaging, because sharpening a single noisy frame just
# makes the noise look worse. Sharpening the clean averaged image is
# fine because there's actual signal there to sharpen.
#
# IMPORTANT: the specimen and the microscope both need to stay
# COMPLETELY STILL for the 1-3 seconds it takes to grab all the frames,
# otherwise the average comes out blurry instead of sharp. Use the
# stand, don't do this handheld.
#
# Controls:
#   q = quit
#   + = zoom in
#   - = zoom out
#   0 = reset zoom/pan
#   w/a/s/d = pan when zoomed in
#   1 = low res (800x600, ~28fps)
#   2 = medium res (1280x960, ~24fps)
#   3 = high res (2048x1536, ~14fps)
#   p = take a normal single-frame snapshot
#   k = take a STACKED snapshot (averages several frames then sharpens)

import cv2
import numpy as np
import os
import time
from datetime import datetime

# where to save pictures
folder_path = os.path.dirname(os.path.abspath(__file__))
save_folder = os.path.join(folder_path, "img")
if not os.path.exists(save_folder):
    os.makedirs(save_folder)

# which camera to open
camera_index = 1

# zoom settings
zoom_min = 1.0
zoom_max = 8.0
zoom_step = 0.5
pan_step = 0.05

# window size on screen
window_width = 960

# text drawing settings
font = cv2.FONT_HERSHEY_SIMPLEX
text_color = (0, 255, 0)
text_size = 0.55
text_thickness = 1

# --- stacking settings ---
# how many frames to average together. more frames = cleaner image but
# takes longer and you have to hold still longer. 16 seems to work well.
stack_frame_count = 16

# how strong the sharpening is after averaging. 1.5 is a decent amount,
# if it still looks soft try raising it a bit, but if you start seeing
# weird bright/dark outlines around edges that means it's too much
sharpen_amount = 1.5
sharpen_radius = 2  # blur amount used to figure out where the edges are


def resize_to_width(img, width):
    h, w = img.shape[:2]
    scale = width / w
    new_w = width
    new_h = int(h * scale)
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


def put_text_top_left(img, text):
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


# copied from my zoom/pan test script, did not change this
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
    return cv2.resize(cropped, (w, h))


# ----------------------------------------------------------------------
# Stacking + sharpening functions - the new stuff
# ----------------------------------------------------------------------

def capture_stack(cap, num_frames):
    # grabs num_frames pictures in a row and averages them together.
    # I add them up as float numbers instead of normal 0-255 numbers,
    # because if I added them as normal numbers they would overflow
    # and wrap around to 0 way before reaching the real total.
    total = None
    frames_added = 0

    for i in range(num_frames):
        success, frame = cap.read()
        if not success:
            continue  # just skip this one if it failed

        frame_as_float = frame.astype(np.float64)

        if total is None:
            total = frame_as_float
        else:
            total = total + frame_as_float

        frames_added = frames_added + 1

        # update the on-screen message so it doesn't look frozen
        show_capturing_message("Stacking frame " + str(i + 1) + "/" + str(num_frames) + "...")

    if frames_added == 0:
        return None

    average = total / frames_added

    # make sure nothing went above 255 or below 0, then convert back
    # to normal image format
    average = np.clip(average, 0, 255)
    average = average.astype(np.uint8)
    return average


def unsharp_mask(image, amount, radius):
    # standard sharpening trick: blur the image, then subtract the
    # blurry version from the original to find the edges, then add
    # those edges back in extra strong. this only looks good because
    # we're doing it on the averaged (already clean) image - doing this
    # on a single noisy frame would just make the grainy noise stand
    # out more
    blurred = cv2.GaussianBlur(image, (0, 0), radius)
    sharpened = cv2.addWeighted(image, 1 + amount, blurred, -amount, 0)
    return sharpened


def show_capturing_message(text):
    # shows a black screen with a message so the app doesn't look
    # frozen while it's busy grabbing frames for the stack
    blank = np.zeros((480, window_width, 3), dtype="uint8")
    (text_w, text_h), _ = cv2.getTextSize(text, font, 1.0, 2)
    x = (window_width - text_w) // 2
    y = (480 + text_h) // 2
    cv2.putText(blank, text, (x, y), font, 1.0, text_color, 2, cv2.LINE_AA)
    cv2.putText(blank, "Keep the specimen and scope still!", (20, 460),
                font, 0.6, (0, 165, 255), 1, cv2.LINE_AA)
    cv2.imshow("Microscope Viewer", blank)
    cv2.waitKey(1)


def open_camera(width, height):
    # closing and reopening the camera is needed because just calling
    # cap.set() on a running camera crashes on my setup
    new_cap = cv2.VideoCapture(camera_index)
    new_cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    new_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return new_cap


def show_switching_screen(width, height):
    blank = np.zeros((480, window_width, 3), dtype="uint8")
    msg = "Switching to " + str(width) + "x" + str(height) + "..."
    (text_w, text_h), _ = cv2.getTextSize(msg, font, 1.0, 2)
    x = (window_width - text_w) // 2
    y = (480 + text_h) // 2
    cv2.putText(blank, msg, (x, y), font, 1.0, text_color, 2, cv2.LINE_AA)
    cv2.imshow("Microscope Viewer", blank)
    cv2.waitKey(1)


# start on resolution 3 (Max detail) since that's probably what you
# want for stacking anyway
res_choice = 3
res_width = 2048
res_height = 1536
res_name = "Max detail"

cap = open_camera(res_width, res_height)

if not cap.isOpened():
    print("Could not open the camera. Check the USB cable and make sure")
    print("no other program is using the camera already.")
    exit()

zoom = zoom_min
pan_x = 0.5
pan_y = 0.5

frame_count = 0
last_fps_time = time.time()
fps = 0.0

print("Controls: q=quit +/-=zoom 0=reset wasd=pan 1/2/3=resolution p=snapshot k=STACK")
print("Saving images to:", save_folder)
print("Stack capture uses", stack_frame_count, "frames averaged together.")

while True:
    success, frame = cap.read()
    if not success:
        continue

    frame_count = frame_count + 1
    now = time.time()
    if now - last_fps_time >= 1.0:
        fps = frame_count / (now - last_fps_time)
        frame_count = 0
        last_fps_time = now

    view = apply_zoom_pan(frame, zoom, pan_x, pan_y)
    displayed = resize_to_width(view, window_width)

    status_text = "%.1f fps   %dx%d (%s)   zoom %.1fx" % (fps, res_width, res_height, res_name, zoom)
    put_text_top_left(displayed, status_text)
    put_text_bottom_left(displayed, "q quit | +/- zoom | 0 reset | wasd pan | 1/2/3 res | p snapshot | k STACK")

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
        # normal single-frame snapshot, full resolution, no zoom/pan
        # baked in, no extra processing
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = "snapshot_" + now_str + ".png"
        full_path = os.path.join(save_folder, filename)
        cv2.imwrite(full_path, frame)
        print("Saved single-frame snapshot (" + str(res_width) + "x" + str(res_height) + "):", full_path)

    elif key == ord('k'):
        # new stacked capture feature
        averaged = capture_stack(cap, stack_frame_count)

        if averaged is None:
            print("Stack capture failed - could not read any frames.")
        else:
            sharpened = unsharp_mask(averaged, sharpen_amount, sharpen_radius)

            now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            raw_filename = "stacked_" + now_str + "_raw.png"
            sharp_filename = "stacked_" + now_str + "_sharpened.png"
            raw_path = os.path.join(save_folder, raw_filename)
            sharp_path = os.path.join(save_folder, sharp_filename)

            # save both versions - the plain averaged one (no sharpening)
            # and the sharpened one. keeping the plain one too in case
            # the sharpening amount needs adjusting later
            cv2.imwrite(raw_path, averaged)
            cv2.imwrite(sharp_path, sharpened)

            print("Saved stacked capture (" + str(stack_frame_count) + " frames, " + str(res_width) + "x" + str(res_height) + "):")
            print("  denoised (no sharpen):", raw_path)
            print("  denoised + sharpened :", sharp_path)

cap.release()
cv2.destroyAllWindows()