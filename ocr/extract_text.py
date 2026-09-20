import pytesseract
import cv2
import os
import sys
import time

sys.path.append(os.path.dirname(__file__))
from preprocess import preprocess_image


def extract_text_direct(image_path):
    """
    Fast path: grayscale + upscale only, no denoising/thresholding.
    Works best on clean, well-lit scans (like most SROIE images).
    """
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"Could not load image at {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    gray = cv2.resize(gray, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)

    custom_config = r'--oem 3 --psm 6'
    return pytesseract.image_to_string(gray, config=custom_config)


def extract_text_preprocessed(image_path):
    """
    Fallback path: full denoise + deskew + threshold pipeline.
    Works better on noisy, textured, or photographed receipts.
    """
    processed = preprocess_image(image_path)
    custom_config = r'--oem 3 --psm 6'
    return pytesseract.image_to_string(processed, config=custom_config)


def extract_text(image_path, min_length_threshold=40):
    """
    Tries the fast direct approach first. If the result looks too short
    (likely garbled/failed OCR), falls back to the full preprocessing pipeline.

    Records which path won in extract_text.last_path and logs the timing of
    each, so a slow capture can be attributed to OCR rather than guessed at.
    """
    t0 = time.perf_counter()
    text = extract_text_direct(image_path)
    fast_secs = time.perf_counter() - t0
    fast_chars = len(text.strip())

    if fast_chars < min_length_threshold:
        t1 = time.perf_counter()
        text = extract_text_preprocessed(image_path)
        slow_secs = time.perf_counter() - t1
        extract_text.last_path = "fallback"
        print(f"  OCR fast {fast_secs:.2f}s -> {fast_chars} chars "
              f"(under {min_length_threshold}); fallback {slow_secs:.2f}s "
              f"-> {len(text.strip())} chars")
    else:
        extract_text.last_path = "fast"
        print(f"  OCR fast {fast_secs:.2f}s -> {fast_chars} chars")

    return text


extract_text.last_path = None


if __name__ == "__main__":
    input_folder = os.path.join("data", "raw")
    output_folder = os.path.join("data", "ocr_text")
    os.makedirs(output_folder, exist_ok=True)

    for filename in os.listdir(input_folder):
        if filename.lower().endswith((".jpg", ".jpeg", ".png")):
            output_filename = os.path.splitext(filename)[0] + ".txt"
            output_path = os.path.join(output_folder, output_filename)

            if os.path.exists(output_path):
                print(f"Skipping (already done): {filename}")
                continue

            image_path = os.path.join(input_folder, filename)
            try:
                text = extract_text(image_path)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"OCR done: {filename}")
            except Exception as e:
                print(f"Failed on {filename}: {e}")