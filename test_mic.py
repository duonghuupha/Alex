import cv2

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Không mở được camera")
else:
    print("Camera mở OK, nhấn Q để thoát")
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        cv2.imshow("Test camera", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cap.release()
    cv2.destroyAllWindows()
