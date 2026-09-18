import json
import os
from database import init_db, insert_receipt

CLASSIFIED_FOLDER = os.path.join("data", "classified")
OCR_TEXT_FOLDER = os.path.join("data", "ocr_text")


def load_all():
    init_db()

    for filename in os.listdir(CLASSIFIED_FOLDER):
        if not filename.endswith(".json"):
            continue

        json_path = os.path.join(CLASSIFIED_FOLDER, filename)
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        base_name = os.path.splitext(filename)[0]
        ocr_text_path = os.path.join(OCR_TEXT_FOLDER, base_name + ".txt")
        ocr_text = ""
        if os.path.exists(ocr_text_path):
            with open(ocr_text_path, "r", encoding="utf-8") as f:
                ocr_text = f.read()

        insert_receipt(
            filename=base_name,
            vendor=data.get("vendor"),
            address=data.get("address"),
            date=data.get("date"),
            total=data.get("total"),
            category=data.get("category"),
            items=data.get("items", []),
            ocr_text=ocr_text
        )
        print(f"Loaded into DB: {base_name}")


if __name__ == "__main__":
    load_all()