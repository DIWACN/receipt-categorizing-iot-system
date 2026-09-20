import ollama
import json
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "db"))
from database import get_all_receipts, update_summary

MODEL_NAME = "gemma2:latest"

SUMMARY_PROMPT_TEMPLATE = """You are writing a short spending summary for one receipt.

Details:
Vendor: {vendor}
Date: {date}
Category: {category}
Total: RM {total}
Items: {items}

Write a short, natural 1-2 sentence summary of this purchase.

Return ONLY a valid JSON object with this exact structure, nothing else:
{{
  "summary_en": "the summary in English",
  "summary_hi": "the same summary translated into Hindi"
}}
"""


def generate_receipt_summary(vendor, date, category, total, items):
    prompt = SUMMARY_PROMPT_TEMPLATE.format(
        vendor=vendor, date=date, category=category,
        total=total, items=items
    )
    response = ollama.generate(model=MODEL_NAME, prompt=prompt)
    raw_output = response["response"].strip()

    try:
        cleaned = raw_output.replace("```json", "").replace("```", "").strip()
        data = json.loads(cleaned)
        return data
    except json.JSONDecodeError:
        print(f"Warning: could not parse summary JSON. Raw output:\n{raw_output}")
        return None


def generate_aggregate_summary(rows):
    total_spent = sum(row[5] for row in rows if row[5] is not None)
    count = len(rows)

    category_totals = {}
    for row in rows:
        cat = row[6]
        amt = row[5] or 0
        category_totals[cat] = category_totals.get(cat, 0) + amt

    category_breakdown = ", ".join(
        f"{cat}: RM {amt:.2f}" for cat, amt in category_totals.items()
    )

    prompt = f"""You are writing an overall spending summary across multiple receipts.

Total receipts: {count}
Total spent: RM {total_spent:.2f}
Breakdown by category: {category_breakdown}

Write a short, natural 2-3 sentence overview of this spending.

Return ONLY a valid JSON object with this exact structure, nothing else:
{{
  "summary_en": "the summary in English",
  "summary_hi": "the same summary translated into Hindi"
}}
"""
    response = ollama.generate(model=MODEL_NAME, prompt=prompt)
    raw_output = response["response"].strip()

    try:
        cleaned = raw_output.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned)
    except json.JSONDecodeError:
        print(f"Warning: could not parse aggregate summary JSON. Raw output:\n{raw_output}")
        return None


if __name__ == "__main__":
    rows = get_all_receipts()
    # Column order: id, filename, vendor, address, date, total, category, items, ocr_text, recommendation_summary, created_at

    for row in rows:
        filename = row[1]
        vendor = row[2]
        date = row[4]
        total = row[5]
        category = row[6]
        items = row[7]
        existing_summary = row[9]

        if existing_summary:
            print(f"Skipping (already summarized): {filename}")
            continue

        print(f"Summarizing: {filename}...")
        summary = generate_receipt_summary(vendor, date, category, total, items)

        if summary:
            summary_json = json.dumps(summary, ensure_ascii=False)
            update_summary(filename, summary_json)
            print(f"  -> EN: {summary.get('summary_en')}")
            print(f"  -> HI: {summary.get('summary_hi')}")
        else:
            print(f"  -> Failed to summarize {filename}")

    print("\nGenerating aggregate summary...")
    aggregate = generate_aggregate_summary(rows)
    if aggregate:
        aggregate_json = json.dumps(aggregate, ensure_ascii=False, indent=2)
        os.makedirs("data", exist_ok=True)
        with open(os.path.join("data", "aggregate_summary.json"), "w", encoding="utf-8") as f:
            f.write(aggregate_json)
        print(f"  -> EN: {aggregate.get('summary_en')}")
        print(f"  -> HI: {aggregate.get('summary_hi')}")
    else:
        print("  -> Failed to generate aggregate summary")