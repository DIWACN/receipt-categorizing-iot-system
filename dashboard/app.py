from flask import Flask, render_template, request, send_from_directory, redirect, url_for
import sys
import os
import json

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "db"))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "ocr"))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "llm"))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "tts"))

from database import get_all_receipts, filter_receipts, insert_receipt, update_summary
from extract_text import extract_text
from classify import classify_receipt
from summarize import generate_receipt_summary, generate_aggregate_summary
from generate_audio import generate_receipt_audio, generate_audio_for_text

app = Flask(__name__)

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
AUDIO_FOLDER = os.path.join(BASE_DIR, "data", "audio")
RAW_FOLDER = os.path.join(BASE_DIR, "data", "raw")


@app.route("/")
def index():
    category = request.args.get("category", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    search_term = request.args.get("search", "").strip()

    if category or date_from or date_to or search_term:
        rows = filter_receipts(
            category=category or None,
            date_from=date_from or None,
            date_to=date_to or None,
            search_term=search_term or None
        )
    else:
        rows = get_all_receipts()

    receipts = []
    for row in rows:
        summary_en, summary_hi = None, None
        if row[8]:
            try:
                parsed = json.loads(row[8])
                summary_en = parsed.get("summary_en")
                summary_hi = parsed.get("summary_hi")
            except (json.JSONDecodeError, TypeError):
                pass

        receipts.append({
            "id": row[0], "filename": row[1], "vendor": row[2], "date": row[3],
            "total": row[4], "category": row[5], "item_list": row[6],
            "summary_en": summary_en, "summary_hi": summary_hi,
        })

    categories = ["groceries", "restaurant", "fuel", "pharmacy",
                  "retail", "electronics", "hardware", "other"]

    aggregate = None
    aggregate_path = os.path.join(BASE_DIR, "data", "aggregate_summary.json")
    if os.path.exists(aggregate_path):
        with open(aggregate_path, "r", encoding="utf-8") as f:
            aggregate = json.load(f)

    return render_template(
        "index.html", receipts=receipts, categories=categories,
        selected_category=category, search_term=search_term,
        date_from=date_from, date_to=date_to, aggregate=aggregate
    )


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("receipt_image")
    if not file or file.filename == "":
        return redirect(url_for("index"))

    os.makedirs(RAW_FOLDER, exist_ok=True)
    filename = file.filename
    save_path = os.path.join(RAW_FOLDER, filename)
    file.save(save_path)

    base_name = os.path.splitext(filename)[0]

    # 1. OCR
    ocr_text = extract_text(save_path)

    # 2. Classify
    result = classify_receipt(ocr_text)
    if not result:
        return redirect(url_for("index"))

    # 3. Store in DB
    insert_receipt(
        filename=base_name,
        vendor=result.get("vendor"),
        date=result.get("date"),
        total=result.get("total"),
        category=result.get("category"),
        items=result.get("items", []),
        ocr_text=ocr_text
    )

    # 4. Summarize this receipt
    summary = generate_receipt_summary(
        result.get("vendor"), result.get("date"),
        result.get("category"), result.get("total"), result.get("items")
    )
    if summary:
        summary_json = json.dumps(summary, ensure_ascii=False)
        update_summary(base_name, summary_json)

        # 5. Generate audio for this receipt
        generate_receipt_audio(base_name, summary_json)

    # 6. Regenerate the aggregate summary + audio so the dashboard reflects the new receipt
    all_rows = get_all_receipts()
    aggregate = generate_aggregate_summary(all_rows)
    if aggregate:
        aggregate_json = json.dumps(aggregate, ensure_ascii=False, indent=2)
        with open(os.path.join(BASE_DIR, "data", "aggregate_summary.json"), "w", encoding="utf-8") as f:
            f.write(aggregate_json)

        en_path = os.path.join(AUDIO_FOLDER, "aggregate_en.mp3")
        hi_path = os.path.join(AUDIO_FOLDER, "aggregate_hi.mp3")
        if aggregate.get("summary_en"):
            generate_audio_for_text(aggregate["summary_en"], "en", en_path)
        if aggregate.get("summary_hi"):
            generate_audio_for_text(aggregate["summary_hi"], "hi", hi_path)

    return redirect(url_for("index"))


@app.route("/audio/<path:filename>")
def serve_audio(filename):
    return send_from_directory(AUDIO_FOLDER, filename)


if __name__ == "__main__":
    app.run(debug=True, port=5000)