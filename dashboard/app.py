from flask import Flask, render_template, request, send_from_directory, redirect, url_for
from werkzeug.utils import secure_filename
from contextlib import contextmanager
import sys
import os
import json
import time
import threading

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "db"))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "ocr"))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "llm"))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "tts"))

from database import (
    get_all_receipts, filter_receipts, insert_receipt, update_summary,
    count_receipts, get_demo_receipts, max_receipt_id, receipt_stats
)
from extract_text import extract_text
from classify import classify_receipt, warm_up
from summarize import generate_receipt_summary, generate_aggregate_summary
from generate_audio import generate_receipt_audio, generate_audio_for_text

app = Flask(__name__)

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
AUDIO_FOLDER = os.path.join(BASE_DIR, "data", "audio")
RAW_FOLDER = os.path.join(BASE_DIR, "data", "raw")
CERT_DIR = os.path.join(BASE_DIR, "certs")

# Demo mode. Nothing is ever deleted: all 39 receipts stay in the database and
# are one click ("Show all") or any search/filter away.
#
#   DEMO_IDS   curated receipt ids to pin, e.g. "76,75,71". Anything captured
#              after the server starts is always shown too, so a live capture
#              lands at the top next to the pinned ones.
#   DEMO_LIMIT used when DEMO_IDS is empty: just the N newest. 0 = show all.
DEMO_IDS = [
    int(x) for x in os.environ.get("DEMO_IDS", "76,75,71").replace(",", " ").split()
]
DEMO_LIMIT = int(os.environ.get("DEMO_LIMIT", "3"))

# Receipts added after this point are demo captures, and always render.
BASELINE_MAX_ID = max_receipt_id()


@app.route("/")
def index():
    category = request.args.get("category", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    search_term = request.args.get("search", "").strip()
    show_all = request.args.get("all") == "1"
    error = request.args.get("error", "").strip()

    total_count, total_spent = receipt_stats()
    limited = False

    if category or date_from or date_to or search_term:
        rows = filter_receipts(
            category=category or None,
            date_from=date_from or None,
            date_to=date_to or None,
            search_term=search_term or None
        )
    elif show_all:
        rows = get_all_receipts()
    elif DEMO_IDS:
        rows = get_demo_receipts(DEMO_IDS, BASELINE_MAX_ID)
        limited = total_count > len(rows)
    elif DEMO_LIMIT > 0:
        rows = get_all_receipts(limit=DEMO_LIMIT)
        limited = total_count > len(rows)
    else:
        rows = get_all_receipts()

    receipts = []
    for row in rows:
        summary_en, summary_hi = None, None
        if row[9]:
            try:
                parsed = json.loads(row[9])
                summary_en = parsed.get("summary_en")
                summary_hi = parsed.get("summary_hi")
            except (json.JSONDecodeError, TypeError):
                pass

        receipts.append({
            "id": row[0], "filename": row[1], "vendor": row[2], "address": row[3],
            "date": row[4], "total": row[5], "category": row[6], "item_list": row[7],
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
        date_from=date_from, date_to=date_to, aggregate=aggregate,
        total_count=total_count, limited=limited, show_all=show_all,
        error=error, new_since=BASELINE_MAX_ID, total_spent=total_spent
    )


@contextmanager
def stage(name, marks):
    """Time one pipeline stage and append (name, seconds) to marks."""
    started = time.perf_counter()
    try:
        yield
    finally:
        marks.append((name, time.perf_counter() - started))


def report(marks, title):
    width = max(len(n) for n, _ in marks)
    print(f"\n  {title}")
    for name, secs in marks:
        print(f"    {name:<{width}}  {secs:6.2f}s")
    print(f"    {'TOTAL':<{width}}  {sum(s for _, s in marks):6.2f}s\n", flush=True)


def regenerate_aggregate():
    """
    Rebuild the aggregate summary + audio from every receipt in the database.
    Each output is written to a temp file and swapped in with os.replace, so a
    page load that lands mid-regeneration reads the previous complete version
    rather than a half-written file.

    ponytail: two uploads in quick succession run this twice and the later one
    wins. Fine for a single-user dashboard; needs a lock if that ever changes.
    """
    marks = []
    with stage("aggregate LLM", marks):
        aggregate = generate_aggregate_summary(get_all_receipts())
    if not aggregate:
        return

    with stage("aggregate JSON", marks):
        path = os.path.join(BASE_DIR, "data", "aggregate_summary.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(aggregate, ensure_ascii=False, indent=2))
        os.replace(tmp, path)

    with stage("aggregate TTS x2", marks):
        for lang in ("en", "hi"):
            text = aggregate.get(f"summary_{lang}")
            if not text:
                continue
            final = os.path.join(AUDIO_FOLDER, f"aggregate_{lang}.mp3")
            tmp_audio = final + ".tmp"
            generate_audio_for_text(text, lang, tmp_audio)
            os.replace(tmp_audio, final)

    report(marks, "BACKGROUND (after the phone already got its response)")


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("receipt_image")
    if not file or file.filename == "":
        return redirect(url_for("index"))

    os.makedirs(RAW_FOLDER, exist_ok=True)

    # secure_filename because this server now listens on 0.0.0.0: an uploaded
    # name like "../../x.jpg" would otherwise escape RAW_FOLDER.
    filename = secure_filename(file.filename) or "receipt.jpg"
    base_name, ext = os.path.splitext(filename)

    # filename is UNIQUE in the receipts table and insert_receipt uses
    # INSERT OR IGNORE, so re-uploading the same file would silently do nothing
    # and look like a failed capture. Give repeats a distinct name instead.
    if os.path.exists(os.path.join(RAW_FOLDER, filename)):
        base_name = f"{base_name}_{int(time.time())}"
        filename = base_name + ext

    marks = []
    save_path = os.path.join(RAW_FOLDER, filename)
    with stage("receive image", marks):
        file.save(save_path)

    # 1. OCR
    with stage("OCR", marks):
        ocr_text = extract_text(save_path)

    # 2. Classify
    with stage("LLM classify", marks):
        result = classify_receipt(ocr_text)
    if not result:
        # Surface the failure instead of redirecting to an unchanged dashboard,
        # which looks identical to "nothing happened".
        return redirect(url_for(
            "index",
            error=f"Could not read that receipt. OCR returned {len(ocr_text.strip())} characters."
        ))

    # 3. Store in DB
    with stage("db insert", marks):
        insert_receipt(
            filename=base_name,
            vendor=result.get("vendor"),
            address=result.get("address"),
            date=result.get("date"),
            total=result.get("total"),
            category=result.get("category"),
            items=result.get("items", []),
            ocr_text=ocr_text,
        )

    # 4. Summarize this receipt
    with stage("LLM summary EN+HI", marks):
        summary = generate_receipt_summary(
            result.get("vendor"), result.get("date"),
            result.get("category"), result.get("total"), result.get("items")
        )
    if summary:
        summary_json = json.dumps(summary, ensure_ascii=False)
        update_summary(base_name, summary_json)

        # 5. Generate audio for this receipt
        with stage("gTTS EN+HI", marks):
            generate_receipt_audio(base_name, summary_json)

    # 6. Regenerate the aggregate in the background and return now.
    #    Measured over three runs: aggregate LLM ~11s + aggregate TTS ~7s, so
    #    ~18s to restate a summary of all receipts that barely moves when one
    #    is added — roughly half the wait if it stayed inline. Off the request
    #    path the phone is freed ~18s sooner; the Overall Summary card is stale
    #    for ~11s (text) to ~18s (audio) and corrects on the next page load.
    threading.Thread(target=regenerate_aggregate, daemon=True).start()

    report(marks, f"FOREGROUND (phone waits on this) — OCR path: {extract_text.last_path}")

    return redirect(url_for("index"))


@app.route("/audio/<path:filename>")
def serve_audio(filename):
    return send_from_directory(AUDIO_FOLDER, filename)


def lan_ip():
    """Best-effort LAN address of this Mac. No traffic is actually sent."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def find_cert():
    """
    Returns (cert, key) from certs/ if a mkcert pair is present, else None.
    mkcert names them '<host>+N.pem' / '<host>+N-key.pem'.
    """
    import glob
    keys = sorted(glob.glob(os.path.join(CERT_DIR, "*-key.pem")))
    if not keys:
        return None
    key = keys[0]
    cert = key.replace("-key.pem", ".pem")
    return (cert, key) if os.path.exists(cert) else None


if __name__ == "__main__":
    ip = lan_ip()
    ssl_context = find_cert()
    scheme = "https" if ssl_context else "http"
    # 5001, not 5000: macOS Control Center (AirPlay Receiver) already holds
    # *:5000, so binding 0.0.0.0:5000 fails with EADDRINUSE.
    port = int(os.environ.get("PORT", "5001"))

    print()
    print("  Receipt Dashboard")
    print(f"    This Mac : {scheme}://localhost:{port}")
    print(f"    Phone    : {scheme}://{ip}:{port}")
    if ssl_context:
        print(f"    Cert     : {os.path.basename(ssl_context[0])}")
        if ip not in os.path.basename(ssl_context[0]):
            print(f"    WARNING  : cert does not cover {ip} — regenerate it:")
            print(f"               cd certs && mkcert {ip} localhost 127.0.0.1")
    else:
        print("    WARNING  : no cert in certs/ — phone cameras need HTTPS.")
        print(f"               cd certs && mkcert {ip} localhost 127.0.0.1")
    if DEMO_IDS:
        print(f"    Showing  : pinned receipts {DEMO_IDS} + anything captured now")
    elif DEMO_LIMIT > 0:
        print(f"    Showing  : the {DEMO_LIMIT} newest receipts")
    else:
        print(f"    Showing  : all {count_receipts()} receipts")
    print('    Override : DEMO_IDS="" DEMO_LIMIT=0 to show everything')
    print()

    # Load gemma2 now rather than on the first capture. Ollama drops an idle
    # model after ~5 min, and that cold load costs the first receipt ~12s.
    print("    Warming  : loading gemma2 into memory…", flush=True)
    threading.Thread(target=warm_up, daemon=True).start()
    print()

    # debug=False on purpose: the reloader restarting mid-upload would kill a
    # 30-second OCR/LLM/TTS run in front of an audience.
    app.run(host="0.0.0.0", port=port, debug=False, ssl_context=ssl_context)