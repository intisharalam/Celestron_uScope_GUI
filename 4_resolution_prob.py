import cv2

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

resolutions_to_test = [
    (320, 240),
    (640, 480),
    (800, 600),
    (1024, 768),
    (1280, 720),
    (1280, 960),
    (1600, 1200),
    (1920, 1080),
    (2048, 1536),
    (2592, 1944),
    (3264, 2448),
    (4000, 3000),
]

already_seen = []

for width, height in resolutions_to_test:
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    ok, frame = cap.read()

    if ok == False:
        print("skipped", width, "x", height, "- camera said no")
        continue

    actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    result = (actual_width, actual_height)

    if result not in already_seen:
        already_seen.append(result)

cap.release()

print("")
print("Resolutions this camera really supports:")
for size in already_seen:
    print(" ", size[0], "x", size[1])


"""
Resolutions this camera really supports:
  640 x 480
  800 x 600
  1280 x 960
  1600 x 1200
  2048 x 1536
"""