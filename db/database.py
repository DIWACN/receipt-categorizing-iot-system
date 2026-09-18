import sqlite3
import os

DB_PATH = os.path.join("db", "receipts.db")


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


def get_all_receipts():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM receipts ORDER BY date DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows


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

    query += " ORDER BY date DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return rows


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")