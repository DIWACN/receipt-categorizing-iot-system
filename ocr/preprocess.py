import cv2
import os
import numpy as np

def preprocess_image(image_path):
    """
    Takes a raw receipt image path, returns a cleaned-up version
    optimized for OCR: grayscale, light denoise, deskewed, thresholded.
    """
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"Could not load image at {image_path}")

    # Step 1: Grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Step 2: Light denoise only (much lower strength than before)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)

    # Step 3: Deskew
    deskewed = deskew_image(denoised)

    # Step 4: Otsu's threshold instead of adaptive — better for clean scans
    _, thresh = cv2.threshold(
        deskewed, 0, 255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    return thresh


def deskew_image(image):
    """
    Detects the dominant text angle and rotates the image to straighten it.
    """
    # Invert so text is white on black (helps contour detection)
    inverted = cv2.bitwise_not(image)

    # Threshold to get a binary image for finding contours
    _, binary = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    # Find all non-zero (text) pixel coordinates
    coords = np.column_stack(np.where(binary > 0))

    if len(coords) == 0:
        return image  # nothing detected, return as-is

    angle = cv2.minAreaRect(coords)[-1]

    # cv2.minAreaRect returns angles in a quirky range; normalize it
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    # Rotate the image to correct the skew
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        image, matrix, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE
    )
    return rotated


if __name__ == "__main__":
    input_folder = os.path.join("data", "raw")
    output_folder = os.path.join("data", "processed")
    os.makedirs(output_folder, exist_ok=True)

    for filename in os.listdir(input_folder):
        if filename.lower().endswith((".jpg", ".jpeg", ".png")):
            input_path = os.path.join(input_folder, filename)
            output_path = os.path.join(output_folder, filename)

            try:
                processed = preprocess_image(input_path)
                cv2.imwrite(output_path, processed)
                print(f"Processed: {filename}")
            except Exception as e:
                print(f"Failed on {filename}: {e}")