import cv2
import os

image_path = os.path.join("data", "raw", "X51005200938.jpg")

image = cv2.imread(image_path)

if image is None:
    print(f"Failed to load image at {image_path}")
else:
    print(f"Loaded image successfully. Shape: {image.shape}")
    os.makedirs(os.path.join("data", "processed"), exist_ok=True)
    cv2.imwrite(os.path.join("data", "processed", "test_output.jpg"), image)
    print("Saved a copy to data/processed/test_output.jpg")