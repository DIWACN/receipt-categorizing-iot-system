# Receipt Categorizing IoT System

An end-to-end pipeline that processes receipt images using OpenCV preprocessing, Tesseract OCR, and a locally hosted LLM (via Ollama) to classify and extract structured data. Results are stored in SQLite and displayed on a Flask dashboard with search/filtering, bilingual (English + Hindi) summaries, and audio playback.

Built for the "Single Board Computers and IoT Applications Development" course assignment, using the SROIE dataset.

## Architecture

```
Receipt Image
     │
     ▼
OpenCV Preprocessing (adaptive: direct grayscale for clean scans,
                       denoise+deskew+threshold fallback for noisy/photographed receipts)
     │
     ▼
Tesseract OCR → raw text
     │
     ▼
Local LLM (gemma2, via Ollama) → structured JSON
   (category, vendor, date, total, items)
     │
     ▼
Deterministic normalization (dates, decimal-comma handling)
     │
     ▼
SQLite Database
     │
     ├──► Flask Dashboard (search, filter, display)
     │
     └──► LLM bilingual summarization (English + Hindi)
              │
              ▼
          gTTS audio generation → playable in dashboard
```
## Project Structure

```
ocr/          - Image preprocessing and text extraction
llm/          - LLM classification and summarization (via Ollama)
db/           - SQLite schema, loading, and query functions
dashboard/    - Flask app + HTML templates
tts/          - Text-to-speech audio generation
data/raw/     - Sample receipt images
```

## Setup

**Prerequisites:**
- Python 3.12+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) (`brew install tesseract` on macOS)
- [Ollama](https://ollama.com) with a local model pulled (`ollama pull gemma2`)

**Install dependencies:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install opencv-python pytesseract pillow ollama flask gtts
```

## Running the pipeline

Run each stage in order (each script skips already-processed files, so it's safe to re-run):

```bash
python ocr/extract_text.py       # OCR on all images in data/raw/
python llm/classify.py           # Classify + extract structured data
python db/database.py            # Initialize the database
python db/load_data.py           # Load classified data into SQLite
python llm/summarize.py          # Generate English + Hindi summaries
python tts/generate_audio.py     # Generate audio for summaries
python dashboard/app.py          # Launch the dashboard
```

The dashboard prints the URLs to use on startup. It listens on **port 5001**,
not 5000: macOS Control Center (AirPlay Receiver) already holds `*:5000`, so
binding `0.0.0.0:5000` fails.

## Capturing from a phone over HTTPS

Mobile browsers only allow camera access in a secure context, so a plain
`http://` LAN address cannot use `getUserMedia` no matter how trusted the
network is. To capture from a phone on the same WiFi:

```bash
brew install mkcert && mkcert -install
```
```bash
mkdir -p certs && cd certs && mkcert "$(ipconfig getifaddr en0)" localhost 127.0.0.1
```

`app.py` picks up any key pair in `certs/` automatically and serves over HTTPS
on `0.0.0.0`. Install `$(mkcert -CAROOT)/rootCA.pem` on the phone and mark it
trusted, then open the `https://<mac-lan-ip>:5001` URL the server prints.
Regenerate the certificate if the Mac's LAN IP changes.

## Demo mode

An unfiltered dashboard shows a small curated set instead of every receipt, so
it loads fast during a live demo. Nothing is deleted; "Show all" and any search
or filter still reach every record.

- `DEMO_IDS`: receipt ids to pin, e.g. `"76,75,71"` (the default). Anything captured after the server starts is always shown too.
- `DEMO_LIMIT`: used when `DEMO_IDS` is empty, shows the N newest.
- Set `DEMO_IDS="" DEMO_LIMIT=0` to show everything.

## Design notes

- **Adaptive OCR strategy**: the pipeline first tries a fast grayscale+upscale approach (works well on clean scans). If the extracted text is too short (a signal of OCR failure), it automatically falls back to a slower denoise+deskew+threshold pipeline, which handles noisy or photographed receipts much better. This was empirically validated on the SROIE dataset and is expected to generalize to real photographed receipts.
- **Deterministic post-processing**: dates and totals are normalized in Python rather than relying on the LLM for exact formatting, since local models proved unreliable at strict formatting tasks (e.g. comma-as-decimal-separator receipts) even with explicit prompting.
- **Local-first LLM**: classification and summarization run entirely through a locally hosted Ollama model, per the assignment's constraints. If deployed on a resource-constrained device (e.g. Raspberry Pi 4), the LLM can instead run on another machine on the same LAN, with the device handling capture/DB/dashboard only.

## Known limitations

- Classification accuracy depends on OCR quality; severely degraded source images (e.g. heavy paper texture/noise covering most of the frame) can still produce unreliable extraction even with the adaptive fallback.
- Local LLM-generated Hindi translations, while generally accurate, are not professionally reviewed.