import os
import pickle
import cv2


def main():
    IMAGE_PATHS = ['carParkImg.png', 'carParkImg.jpg', 'carParkImg.jpeg']
    img = None
    for image_path in IMAGE_PATHS:
        if os.path.exists(image_path):
            img = cv2.imread(image_path)
            if img is not None:
                break

    if img is None:
        raise FileNotFoundError(
            'Could not load parking lot image. Checked: ' + ', '.join(IMAGE_PATHS)
        )

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 1)
    thresh = cv2.adaptiveThreshold(
        blur,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        25,
        16
    )

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilate = cv2.dilate(thresh, kernel, iterations=1)

    contours, _ = cv2.findContours(
        dilate,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    posList = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 1000:
            x, y, w, h = cv2.boundingRect(cnt)
            if w > 50 and h > 20:
                posList.append((x, y))
                cv2.rectangle(
                    img,
                    (x, y),
                    (x + w, y + h),
                    (0, 255, 0),
                    2
                )

    with open('CarParkPos', 'wb') as f:
        pickle.dump(posList, f)

    print("Parking slots auto-detected and saved!")

    cv2.imshow("Detected Parking Slots", img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()