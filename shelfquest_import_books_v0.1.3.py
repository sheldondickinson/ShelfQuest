#!/usr/bin/env python3
"""
ShelfQuest CSV importer v0.1.3.

Expected CSV columns:
  ISBN, Barcode, Qty, Title, Author, Illustrator, Synopsis, Category, CoverURL

Usage inside the ShelfQuest container:
  python /data/import_books.py /data/kids-library.csv --dry-run
  python /data/import_books.py /data/kids-library.csv

Behaviour:
- Barcode is the scannable physical-copy code.
- If Barcode is blank, ISBN is used as the temporary scannable code.
- ISBN is stored on the book/title record for metadata lookup and ISBN fallback scanning.
- Qty is stored on the book/title record as owned_qty.
- Duplicate ISBN rows are allowed when they have different Barcode values.
- Duplicate Barcode rows are skipped because a barcode must identify one physical copy.
"""
import argparse
import csv
import json
import os
import re
import sqlite3
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = os.getenv("LIBRARY_DB", "/data/library.db")
DEFAULT_CSV = "/data/kids-library.csv"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clean_isbn(value):
    value = str(value or "").strip().upper()
    return "".join(ch for ch in value if ch.isdigit() or ch == "X")


def clean_text(value):
    return str(value or "").strip()


def clean_int(value, default=1):
    try:
        n = int(float(str(value or "").strip()))
        return n if n > 0 else default
    except Exception:
        return default


def clean_barcode(value, fallback_isbn=""):
    """Preserve custom barcode values, but normalise typed ISBN-style barcodes."""
    raw = str(value or "").strip()
    if not raw:
        return fallback_isbn
    compact = re.sub(r"\s+", "", raw)

    # If someone typed an ISBN/EAN barcode with spaces or hyphens, store the scanner-equivalent digits.
    isbnish = clean_isbn(compact)
    if isbnish and re.fullmatch(r"[0-9Xx\-\s]+", raw) and len(isbnish) >= 8:
        return isbnish

    return compact


def lookup_isbn(isbn):
    try:
        url = "https://www.googleapis.com/books/v1/volumes?q=" + urllib.parse.quote(f"isbn:{isbn}")
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("items") or []
        if items:
            info = items[0].get("volumeInfo", {})
            return {
                "title": clean_text(info.get("title")),
                "author": ", ".join(info.get("authors") or []),
                "cover_url": (info.get("imageLinks") or {}).get("thumbnail") or "",
                "category": ", ".join(info.get("categories") or []),
                "synopsis": clean_text(info.get("description")),
                "source": "google_books",
            }
    except Exception:
        pass
    try:
        url = f"https://openlibrary.org/isbn/{urllib.parse.quote(isbn)}.json"
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {
            "title": clean_text(data.get("title")),
            "author": "",
            "cover_url": f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg",
            "category": "",
            "synopsis": "",
            "source": "open_library",
        }
    except Exception:
        return {}


def column_exists(conn, table, column):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def ensure_schema(conn):
    additions = {
        "illustrator": "ALTER TABLE books ADD COLUMN illustrator TEXT",
        "synopsis": "ALTER TABLE books ADD COLUMN synopsis TEXT",
        "owned_qty": "ALTER TABLE books ADD COLUMN owned_qty INTEGER NOT NULL DEFAULT 1",
    }
    for col, sql in additions.items():
        if not column_exists(conn, "books", col):
            conn.execute(sql)


def get_field(row, name):
    wanted = name.strip().lower()
    aliases = {
        "coverurl": {"coverurl", "cover url", "cover_url", "cover"},
        "qty": {"qty", "quantity", "owned_qty", "owned qty", "copies"},
        "barcode": {"barcode", "bar code", "copy barcode", "copy_barcode", "internal barcode", "internal_barcode", "scan code", "scancode"},
    }.get(wanted, {wanted})
    for key, value in row.items():
        k = str(key or "").strip().lower().replace("_", " ")
        compact = k.replace(" ", "")
        if k in aliases or compact in aliases:
            return value
    return ""


def choose_unknown_title(isbn, barcode):
    if isbn:
        return f"Unknown title ({isbn})"
    return f"Unknown title ({barcode})"


def upsert_book(conn, *, isbn, title, author, illustrator, synopsis, cover_url, category, owned_qty, dry_run):
    if isbn:
        existing = conn.execute("SELECT * FROM books WHERE isbn = ?", (isbn,)).fetchone()
    else:
        existing = None

    if existing:
        book_id = existing["id"]
        if not dry_run:
            conn.execute(
                """
                UPDATE books
                SET title = CASE WHEN title IS NULL OR title = '' OR title LIKE 'Unknown title (%' THEN ? ELSE title END,
                    author = CASE WHEN (author IS NULL OR author = '') AND ? != '' THEN ? ELSE author END,
                    illustrator = CASE WHEN (illustrator IS NULL OR illustrator = '') AND ? != '' THEN ? ELSE illustrator END,
                    synopsis = CASE WHEN (synopsis IS NULL OR synopsis = '') AND ? != '' THEN ? ELSE synopsis END,
                    cover_url = CASE WHEN (cover_url IS NULL OR cover_url = '') AND ? != '' THEN ? ELSE cover_url END,
                    category = CASE WHEN (category IS NULL OR category = '') AND ? != '' THEN ? ELSE category END,
                    owned_qty = CASE WHEN owned_qty < ? THEN ? ELSE owned_qty END
                WHERE id = ?
                """,
                (
                    title,
                    author, author,
                    illustrator, illustrator,
                    synopsis, synopsis,
                    cover_url, cover_url,
                    category, category,
                    owned_qty, owned_qty,
                    book_id,
                ),
            )
        return book_id, False

    if dry_run:
        return -1, True

    cur = conn.execute(
        """
        INSERT INTO books(isbn, title, author, illustrator, synopsis, cover_url, category, reading_level, owned_qty, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (isbn or None, title, author or None, illustrator or None, synopsis or None, cover_url or None, category or None, None, owned_qty, now_iso()),
    )
    return cur.lastrowid, True


def upsert_copy(conn, *, book_id, isbn, barcode, title, dry_run):
    existing_barcode = conn.execute("SELECT id, book_id FROM book_copies WHERE barcode = ?", (barcode,)).fetchone()
    if existing_barcode:
        if book_id != -1 and existing_barcode["book_id"] != book_id:
            return "conflict", existing_barcode["id"]
        return "existing", existing_barcode["id"]

    # If this book previously had only the ISBN as a temporary barcode, replace it with
    # the new explicit barcode. ISBN fallback scanning still works via books.isbn.
    if isbn and barcode != isbn and book_id != -1:
        isbn_copy = conn.execute(
            "SELECT id FROM book_copies WHERE book_id = ? AND barcode = ?",
            (book_id, isbn),
        ).fetchone()
        if isbn_copy:
            if not dry_run:
                conn.execute("UPDATE book_copies SET barcode = ? WHERE id = ?", (barcode, isbn_copy["id"]))
                conn.execute(
                    "INSERT INTO events(event_type, book_copy_id, notes, created_at) VALUES (?, ?, ?, ?)",
                    ("book_copy_relabelled", isbn_copy["id"], f"{isbn} -> {barcode}", now_iso()),
                )
            return "relabelled", isbn_copy["id"]

    if not dry_run:
        cur = conn.execute(
            "INSERT INTO book_copies(book_id, barcode, created_at) VALUES (?, ?, ?)",
            (book_id, barcode, now_iso()),
        )
        conn.execute(
            "INSERT INTO events(event_type, book_copy_id, notes, created_at) VALUES (?, ?, ?, ?)",
            ("book_imported", cur.lastrowid, title, now_iso()),
        )
        return "inserted", cur.lastrowid
    return "inserted", -1


def import_csv(csv_path, dry_run=False, lookup_missing=False):
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")
    if not Path(DB_PATH).exists():
        raise SystemExit(f"ShelfQuest database not found: {DB_PATH}. Is the app running?")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    # Pre-count distinct barcodes per ISBN so owned_qty can reflect row-per-copy spreadsheets.
    barcodes_by_isbn = defaultdict(set)
    max_qty_by_isbn = defaultdict(lambda: 1)
    prepared_rows = []

    for idx, row in enumerate(rows, start=2):
        isbn = clean_isbn(get_field(row, "ISBN"))
        barcode = clean_barcode(get_field(row, "Barcode"), fallback_isbn=isbn)
        qty = clean_int(get_field(row, "Qty"), 1)
        if isbn:
            if barcode:
                barcodes_by_isbn[isbn].add(barcode)
            max_qty_by_isbn[isbn] = max(max_qty_by_isbn[isbn], qty)
        prepared_rows.append((idx, row, isbn, barcode, qty))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)

    inserted_books = 0
    updated_books = 0
    inserted_copies = 0
    existing_copies = 0
    relabelled_copies = 0
    barcode_conflicts = []
    duplicate_barcode_rows = []
    skipped_rows = []
    unknown_titles = []
    looked_up = []
    seen_barcodes = set()

    try:
        for idx, row, isbn, barcode, qty in prepared_rows:
            title = clean_text(get_field(row, "Title"))
            author = clean_text(get_field(row, "Author"))
            illustrator = clean_text(get_field(row, "Illustrator"))
            synopsis = clean_text(get_field(row, "Synopsis"))
            category = clean_text(get_field(row, "Category"))
            cover_url = clean_text(get_field(row, "CoverURL"))

            if not barcode:
                skipped_rows.append((idx, "missing both ISBN and Barcode"))
                continue

            if barcode in seen_barcodes:
                duplicate_barcode_rows.append((idx, barcode, title or "<blank title>"))
                continue
            seen_barcodes.add(barcode)

            if isbn:
                owned_qty = max(qty, max_qty_by_isbn[isbn], len(barcodes_by_isbn[isbn]) or 1)
            else:
                owned_qty = qty

            if isbn and (not title or not author or not cover_url) and lookup_missing:
                meta = lookup_isbn(isbn)
                if meta:
                    if not title and meta.get("title"):
                        title = meta["title"]
                    if not author and meta.get("author"):
                        author = meta["author"]
                    if not cover_url and meta.get("cover_url"):
                        cover_url = meta["cover_url"]
                    if not category and meta.get("category"):
                        category = meta["category"]
                    if not synopsis and meta.get("synopsis"):
                        synopsis = meta["synopsis"]
                    looked_up.append((idx, isbn, title or "<blank>", meta.get("source", "lookup")))

            if not title:
                title = choose_unknown_title(isbn, barcode)
                unknown_titles.append((idx, isbn or barcode))

            book_id, is_new = upsert_book(
                conn,
                isbn=isbn,
                title=title,
                author=author,
                illustrator=illustrator,
                synopsis=synopsis,
                cover_url=cover_url,
                category=category,
                owned_qty=owned_qty,
                dry_run=dry_run,
            )
            if is_new:
                inserted_books += 1
            else:
                updated_books += 1

            status, copy_id = upsert_copy(conn, book_id=book_id, isbn=isbn, barcode=barcode, title=title, dry_run=dry_run)
            if status == "inserted":
                inserted_copies += 1
            elif status == "existing":
                existing_copies += 1
            elif status == "relabelled":
                relabelled_copies += 1
            elif status == "conflict":
                barcode_conflicts.append((idx, barcode, title))

        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    finally:
        conn.close()

    print("ShelfQuest import complete" if not dry_run else "ShelfQuest dry-run complete")
    print(f"CSV rows read:                 {len(rows)}")
    print(f"Books inserted:                {inserted_books}")
    print(f"Existing books updated:        {updated_books}")
    print(f"Scannable copies inserted:     {inserted_copies}")
    print(f"Existing copies left as-is:    {existing_copies}")
    print(f"ISBN copies relabelled:        {relabelled_copies}")
    print(f"Duplicate barcode rows skipped:{len(duplicate_barcode_rows)}")
    print(f"Barcode conflicts:             {len(barcode_conflicts)}")
    print(f"Rows skipped:                  {len(skipped_rows)}")
    print(f"Rows looked up online:         {len(looked_up)}")
    print(f"Fallback unknown titles:       {len(unknown_titles)}")
    print("\nBarcode handling: Barcode is the scannable copy code. If blank, ISBN is used. ISBN fallback scanning still works from the book record.")

    if duplicate_barcode_rows:
        print("\nDuplicate Barcode rows skipped:")
        for line, barcode, title in duplicate_barcode_rows[:30]:
            print(f"  line {line}: {barcode} - {title}")
        if len(duplicate_barcode_rows) > 30:
            print(f"  ... plus {len(duplicate_barcode_rows) - 30} more")

    if barcode_conflicts:
        print("\nBarcode conflicts requiring manual review:")
        for line, barcode, title in barcode_conflicts[:30]:
            print(f"  line {line}: {barcode} - {title}")

    if unknown_titles:
        print("\nRows imported with fallback Unknown title:")
        for line, ref in unknown_titles[:30]:
            print(f"  line {line}: {ref}")

    if skipped_rows:
        print("\nRows skipped:")
        for line, reason in skipped_rows[:30]:
            print(f"  line {line}: {reason}")


def main():
    parser = argparse.ArgumentParser(description="Import a Kids Library CSV into ShelfQuest.")
    parser.add_argument("csv_path", nargs="?", default=DEFAULT_CSV)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--lookup-missing", action="store_true", help="Try online ISBN lookup for missing title/author/cover/category/synopsis")
    args = parser.parse_args()
    import_csv(args.csv_path, dry_run=args.dry_run, lookup_missing=args.lookup_missing)


if __name__ == "__main__":
    main()
