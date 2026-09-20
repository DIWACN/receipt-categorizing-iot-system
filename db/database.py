import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "receipts.db")


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT UNIQUE,
        vendor TEXT,
        address TEXT,
        date TEXT,
        total REAL,
        category TEXT,
        items TEXT,
        ocr_text TEXT,
        recommendation_summary TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
""")
    conn.commit()
    conn.close()


def insert_receipt(filename, vendor, address, date, total, category, items, ocr_text, recommendation_summary=None):
    """
    Inserts one receipt record. Uses INSERT OR IGNORE so re-running the
    loader never wipes an existing receipt's recommendation_summary.
    """
    conn = get_connection()
    cursor = conn.cursor()
    items_str = ", ".join(items) if items else ""

    cursor.execute("""
        INSERT OR IGNORE INTO receipts
        (filename, vendor, address, date, total, category, items, ocr_text, recommendation_summary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (filename, vendor, address, date, total, category, items_str, ocr_text, recommendation_summary))

    conn.commit()
    conn.close()


def update_summary(filename, recommendation_summary):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE receipts SET recommendation_summary = ? WHERE filename = ?
    """, (recommendation_summary, filename))
    conn.commit()
    conn.close()


def get_receipt_by_filename(filename):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM receipts WHERE filename = ?", (filename,))
    row = cursor.fetchone()
    conn.close()
    return row


def get_all_receipts(limit=None):
    """
    Returns receipts newest-first. Ordering is by id, not date: the date
    column holds raw OCR strings that are not always parseable
    (e.g. "Frid=w, 29-12-2017"), so a date sort would not reliably put a
    freshly captured receipt first.
    """
    conn = get_connection()
    cursor = conn.cursor()
    if limit is None:
        cursor.execute("SELECT * FROM receipts ORDER BY id DESC")
    else:
        cursor.execute("SELECT * FROM receipts ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_demo_receipts(pinned_ids, since_id):
    """
    The curated demo view: a fixed set of pinned receipts, plus every receipt
    added after since_id (i.e. anything captured live during the demo).
    Newest first.
    """
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in pinned_ids) or "NULL"
    cursor.execute(
        f"SELECT * FROM receipts WHERE id IN ({placeholders}) OR id > ? "
        "ORDER BY id DESC",
        (*pinned_ids, since_id),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def max_receipt_id():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(MAX(id), 0) FROM receipts")
    value = cursor.fetchone()[0]
    conn.close()
    return value


def count_receipts():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM receipts")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def receipt_stats():
    """(count, total spent) across every receipt, for the ledger header."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(total), 0) FROM receipts")
    count, total = cursor.fetchone()
    conn.close()
    return count, total


def filter_receipts(category=None, date_from=None, date_to=None, search_term=None):
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM receipts WHERE 1=1"
    params = []

    if category:
        query += " AND category = ?"
        params.append(category)
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    if search_term:
        query += " AND (vendor LIKE ? OR items LIKE ? OR ocr_text LIKE ?)"
        like_term = f"%{search_term}%"
        params.extend([like_term, like_term, like_term])

    query += " ORDER BY id DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return rows


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")