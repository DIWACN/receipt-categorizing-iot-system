import ollama
import os
import json
import re
from datetime import datetime

MODEL_NAME = "gemma2:latest"

CATEGORIES = [
    "groceries", "restaurant", "fuel", "pharmacy",
    "retail", "electronics", "hardware", "other"
]

PROMPT_TEMPLATE = """You are extracting structured data from a receipt's OCR text.
The OCR text may contain minor errors (misread characters, garbled words) - use context to infer the correct values where possible.

Classify the receipt into exactly ONE of these categories: {categories}

Return ONLY a valid JSON object with this exact structure, and nothing else - no explanation, no markdown formatting:
{{
  "category": "one of the categories listed above",
  "vendor": "the store or business name",
  "address": "the store's address as it appears in the text, or null if not present",
  "date": "the transaction date, as it appears in the text",
  "total": "the final total amount, as it appears in the text",
  "items": ["short list of item names purchased"]
}}

OCR text:
{ocr_text}
"""


def normalize_total(total_value):
    if total_value is None:
        return None

    s = str(total_value).strip()
    s = re.sub(r"[^\d.,]", "", s)
    s = s.replace(",", ".")

    if s.count(".") > 1:
        parts = s.split(".")
        s = "".join(parts[:-1]) + "." + parts[-1]

    try:
        value = float(s)
    except ValueError:
        return None

    if value > 1000 and "." not in s:
        value = value / 100

    return round(value, 2)


def normalize_date(date_value):
    if date_value is None:
        return None

    date_str = str(date_value).strip()
    formats_to_try = [
        "%Y-%m-%d", "%d-%m-%y", "%d-%m-%Y",
        "%d/%m/%Y", "%d/%m/%y", "%m-%d-%y",
        "%d/%m/%Y %I:%M:%S %p", "%d-%m-%Y %H:%M:%S"
    ]
    for fmt in formats_to_try:
        try:
            parsed = datetime.strptime(date_str, fmt)
            if parsed.year < 100:
                parsed = parsed.replace(year=parsed.year + 2000)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str


def warm_up():
    """
    Pull the model into memory with a throwaway generation.

    Ollama unloads an idle model after ~5 minutes. Measured, that costs the
    first capture about 12 extra seconds inside classify_receipt (21.7s cold
    versus 9.9s warm), which would land on the first receipt of a live demo.
    """
    try:
        ollama.generate(model=MODEL_NAME, prompt="ok", options={"num_predict": 1})
        return True
    except Exception as exc:
        print(f"  model warm-up failed ({exc}); first capture will be slower")
        return False


def classify_receipt(ocr_text):
    prompt = PROMPT_TEMPLATE.format(
        categories=", ".join(CATEGORIES),
        ocr_text=ocr_text
    )

    response = ollama.generate(model=MODEL_NAME, prompt=prompt)
    raw_output = response["response"].strip()

    try:
        cleaned = raw_output.replace("```json", "").replace("```", "").strip()
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        print(f"Warning: could not parse JSON. Raw output:\n{raw_output}")
        return None

    data["total"] = normalize_total(data.get("total"))
    data["date"] = normalize_date(data.get("date"))

    return data


if __name__ == "__main__":
    ocr_folder = os.path.join("data", "ocr_text")
    output_folder = os.path.join("data", "classified")
    os.makedirs(output_folder, exist_ok=True)

    for filename in os.listdir(ocr_folder):
        if filename.endswith(".txt"):
            output_filename = os.path.splitext(filename)[0] + ".json"
            output_path = os.path.join(output_folder, output_filename)

            if os.path.exists(output_path):
                print(f"Skipping (already done): {filename}")
                continue

            filepath = os.path.join(ocr_folder, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                ocr_text = f.read()

            print(f"Classifying: {filename}...")
            result = classify_receipt(ocr_text)

            if result:
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2)
                print(f"  -> {result.get('category')}, {result.get('vendor')}, {result.get('total')}")
            else:
                print(f"  -> Failed to classify {filename}")