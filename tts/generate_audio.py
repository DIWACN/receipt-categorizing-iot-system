from gtts import gTTS
import json
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "db"))
from database import get_all_receipts

AUDIO_FOLDER = os.path.join("data", "audio")


def generate_audio_for_text(text, lang_code, output_path):
    tts = gTTS(text=text, lang=lang_code)
    tts.save(output_path)


def generate_receipt_audio(filename, recommendation_summary_json):
    en_path = os.path.join(AUDIO_FOLDER, f"{filename}_en.mp3")
    hi_path = os.path.join(AUDIO_FOLDER, f"{filename}_hi.mp3")

    if os.path.exists(en_path) and os.path.exists(hi_path):
        print(f"  -> Skipping (already done): {filename}")
        return

    try:
        summary = json.loads(recommendation_summary_json)
    except (json.JSONDecodeError, TypeError):
        print(f"  -> No valid summary found for {filename}, skipping")
        return

    en_text = summary.get("summary_en")
    hi_text = summary.get("summary_hi")

    if en_text and not os.path.exists(en_path):
        generate_audio_for_text(en_text, "en", en_path)

    if hi_text and not os.path.exists(hi_path):
        generate_audio_for_text(hi_text, "hi", hi_path)


if __name__ == "__main__":
    os.makedirs(AUDIO_FOLDER, exist_ok=True)

    rows = get_all_receipts()

    for row in rows:
        filename = row[1]
        recommendation_summary = row[8]

        print(f"Generating audio: {filename}...")
        generate_receipt_audio(filename, recommendation_summary)

    aggregate_path = os.path.join("data", "aggregate_summary.json")
    if os.path.exists(aggregate_path):
        print("Generating audio: aggregate summary...")
        with open(aggregate_path, "r", encoding="utf-8") as f:
            aggregate = json.load(f)

        en_text = aggregate.get("summary_en")
        hi_text = aggregate.get("summary_hi")

        en_agg_path = os.path.join(AUDIO_FOLDER, "aggregate_en.mp3")
        hi_agg_path = os.path.join(AUDIO_FOLDER, "aggregate_hi.mp3")

        if en_text and not os.path.exists(en_agg_path):
            generate_audio_for_text(en_text, "en", en_agg_path)
        if hi_text and not os.path.exists(hi_agg_path):
            generate_audio_for_text(hi_text, "hi", hi_agg_path)

    print("Done.")