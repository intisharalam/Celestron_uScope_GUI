import cv2

cap = cv2.VideoCapture(1)   # open camera 1 and 0 is in-built laptop webcam
while True:
    ok, frame = cap.read()  # ok=T/F if camera worked; frame = image read (np.array)
    
    if not ok:
        break
    
    cv2.imshow("Microscope", frame) # draw the frame/image (np.array)

    # adds 1ms delay, else doesn't work    
    if cv2.waitKey(1) == ord('q'):  # wait 1ms for quit command
        break

# if not done, prevents rerunning of script without replugging camera
cap.release()   # frees camera resource
cv2.destroyAllWindows() # clears all windows from cv2
