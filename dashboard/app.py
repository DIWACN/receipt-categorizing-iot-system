from flask import Flask, render_template, request, send_from_directory
import sys
import os
import json

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "db"))
from database import get_all_receipts, filter_receipts

app = Flask(__name__)

AUDIO_FOLDER = os.path.join(os.path.dirname(__file__), "..", "data", "audio")


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

    # Column order: id, filename, vendor, date, total, category, items, ocr_text, recommendation_summary, created_at
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
            "id": row[0],
            "filename": row[1],
            "vendor": row[2],
            "date": row[3],
            "total": row[4],
            "category": row[5],
            "item_list": row[6],
            "summary_en": summary_en,
            "summary_hi": summary_hi,
        })

    categories = ["groceries", "restaurant", "fuel", "pharmacy",
                  "retail", "electronics", "hardware", "other"]

    # Load aggregate summary if it exists
    aggregate = None
    aggregate_path = os.path.join(os.path.dirname(__file__), "..", "data", "aggregate_summary.json")
    if os.path.exists(aggregate_path):
        with open(aggregate_path, "r", encoding="utf-8") as f:
            aggregate = json.load(f)

    return render_template(
        "index.html",
        receipts=receipts,
        categories=categories,
        selected_category=category,
        search_term=search_term,
        date_from=date_from,
        date_to=date_to,
        aggregate=aggregate
    )


@app.route("/audio/<path:filename>")
def serve_audio(filename):
    return send_from_directory(AUDIO_FOLDER, filename)


if __name__ == "__main__":
    app.run(debug=True, port=5000)