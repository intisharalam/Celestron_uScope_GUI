import cv2

cap = cv2.VideoCapture(1)

zoom = 1.0
pan_x, pan_y = 0.5, 0.5

def apply_zoom_pan(frame, zoom, pan_x, pan_y):
    if zoom <= 1.0:
        return frame
    
    # find new height and width
    h, w = frame.shape[:2]
    crop_w = w / zoom
    crop_h = h / zoom

    # find new centre of image
    cx = pan_x * w
    cy = pan_y * h

    # coordinates of top-left and bottom-right
    x_start = int(max(0, min(w - crop_w, cx -crop_w/2)))
    y_start = int(max(0, min(h - crop_w, cy -crop_h/2)))
    x_end = int(x_start + crop_w)
    y_end = int(y_start + crop_h)

    cropped = frame[y_start:y_end, x_start:x_end]
    
    # resize to original frame size (else looks like a cutout)
    return cv2.resize(cropped, (w,h))   

while True:
    ok, frame = cap.read()
    if not ok:
        break

    view = apply_zoom_pan(frame, zoom, pan_x, pan_y)
    cv2.imshow("Zoom/Pan Test", view)

    # key returns 32-bit integer. We only car about 8-bit LSB.
    # We mask with: 
    # 0000 0000 0000 0000      0000 0000 1111 1111
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('+') or key == ord('='):
        zoom = min(8.0, zoom + 0.5)
    elif key == ord('-'):
        zoom = max(1.0, zoom - 0.5)
    elif key == ord('0'):
        zoom, pan_x, pan_y = 1.0, 0.5, 0.5
    elif key == ord('w'):
        pan_y = max(0.0, pan_y - 0.05)
    elif key == ord('s'):
        pan_y = min(1.0, pan_y + 0.05)
    elif key == ord('a'):
        pan_x = max(0.0, pan_x - 0.05)
    elif key == ord('d'):
        pan_x = min(1.0, pan_x + 0.05)

cap.release()
cv2.destroyAllWindows()