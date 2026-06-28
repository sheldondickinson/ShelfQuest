import os
import sqlite3
import urllib.parse
import urllib.request
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

DB_PATH = os.getenv("LIBRARY_DB", "/data/library.db")
DEFAULT_LOAN_DAYS = int(os.getenv("DEFAULT_LOAN_DAYS", "7"))
APP_DIR = Path(__file__).resolve().parent

app = FastAPI(title="ShelfQuest", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def db() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS children (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                barcode TEXT NOT NULL UNIQUE,
                borrow_limit INTEGER NOT NULL DEFAULT 5,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                isbn TEXT UNIQUE,
                title TEXT NOT NULL,
                author TEXT,
                cover_url TEXT,
                category TEXT,
                reading_level TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS book_copies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                barcode TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'available',
                shelf_location TEXT,
                condition_note TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS loans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_copy_id INTEGER NOT NULL,
                child_id INTEGER NOT NULL,
                borrowed_at TEXT NOT NULL,
                due_at TEXT NOT NULL,
                returned_at TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                FOREIGN KEY(book_copy_id) REFERENCES book_copies(id),
                FOREIGN KEY(child_id) REFERENCES children(id)
            );

            CREATE INDEX IF NOT EXISTS idx_loans_active_copy
                ON loans(book_copy_id, status);

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                child_id INTEGER,
                book_copy_id INTEGER,
                notes TEXT,
                created_at TEXT NOT NULL
            );
            """
        )


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def root():
    return FileResponse(str(APP_DIR / "static" / "index.html"))


class ChildIn(BaseModel):
    name: str = Field(min_length=1)
    barcode: str = Field(min_length=1)
    borrow_limit: int = Field(default=5, ge=1, le=50)


class BookIn(BaseModel):
    isbn: Optional[str] = None
    title: str = Field(min_length=1)
    author: Optional[str] = None
    cover_url: Optional[str] = None
    category: Optional[str] = None
    reading_level: Optional[str] = None
    barcode: Optional[str] = None


class CheckoutIn(BaseModel):
    child_barcode: str
    book_code: str


class ReturnIn(BaseModel):
    book_code: str


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


@app.get("/api/health")
def health():
    return {"ok": True, "db": DB_PATH}


@app.post("/api/children")
def add_child(child: ChildIn):
    try:
        with db() as conn:
            cur = conn.execute(
                "INSERT INTO children(name, barcode, borrow_limit, created_at) VALUES (?, ?, ?, ?)",
                (child.name.strip(), child.barcode.strip(), child.borrow_limit, now_iso()),
            )
            conn.execute(
                "INSERT INTO events(event_type, child_id, notes, created_at) VALUES (?, ?, ?, ?)",
                ("child_created", cur.lastrowid, child.name.strip(), now_iso()),
            )
        return {"ok": True, "id": cur.lastrowid}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Child barcode already exists")


@app.get("/api/children")
def list_children():
    with db() as conn:
        rows = conn.execute(
            """
            SELECT c.*,
                   COUNT(l.id) AS active_loans
            FROM children c
            LEFT JOIN loans l ON l.child_id = c.id AND l.status = 'active'
            WHERE c.active = 1
            GROUP BY c.id
            ORDER BY c.name
            """
        ).fetchall()
    return rows_to_dicts(rows)


@app.get("/api/children/by-barcode/{barcode}")
def child_by_barcode(barcode: str):
    with db() as conn:
        row = conn.execute("SELECT * FROM children WHERE barcode = ? AND active = 1", (barcode,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Child card not found")
    return dict(row)


@app.get("/api/lookup/{isbn}")
def lookup_isbn(isbn: str):
    cleaned = "".join(ch for ch in isbn if ch.isdigit() or ch.upper() == "X")
    if not cleaned:
        raise HTTPException(status_code=400, detail="Invalid ISBN")

    # Google Books first
    try:
        url = "https://www.googleapis.com/books/v1/volumes?q=" + urllib.parse.quote(f"isbn:{cleaned}")
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("items") or []
        if items:
            info = items[0].get("volumeInfo", {})
            return {
                "isbn": cleaned,
                "title": info.get("title") or "",
                "author": ", ".join(info.get("authors") or []),
                "cover_url": (info.get("imageLinks") or {}).get("thumbnail"),
                "source": "google_books",
            }
    except Exception:
        pass

    # Open Library fallback
    try:
        url = f"https://openlibrary.org/isbn/{urllib.parse.quote(cleaned)}.json"
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {
            "isbn": cleaned,
            "title": data.get("title") or "",
            "author": None,
            "cover_url": f"https://covers.openlibrary.org/b/isbn/{cleaned}-M.jpg",
            "source": "open_library",
        }
    except Exception:
        raise HTTPException(status_code=404, detail="No metadata found. Add manually.")


@app.post("/api/books")
def add_book(book: BookIn):
    isbn = book.isbn.strip() if book.isbn else None
    barcode = (book.barcode or isbn or "").strip()
    if not barcode:
        raise HTTPException(status_code=400, detail="A barcode or ISBN is required")

    try:
        with db() as conn:
            existing = conn.execute("SELECT id FROM books WHERE isbn = ?", (isbn,)).fetchone() if isbn else None
            if existing:
                book_id = existing["id"]
            else:
                cur = conn.execute(
                    """
                    INSERT INTO books(isbn, title, author, cover_url, category, reading_level, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        isbn,
                        book.title.strip(),
                        (book.author or "").strip() or None,
                        book.cover_url,
                        book.category,
                        book.reading_level,
                        now_iso(),
                    ),
                )
                book_id = cur.lastrowid

            cur2 = conn.execute(
                "INSERT INTO book_copies(book_id, barcode, created_at) VALUES (?, ?, ?)",
                (book_id, barcode, now_iso()),
            )
            conn.execute(
                "INSERT INTO events(event_type, book_copy_id, notes, created_at) VALUES (?, ?, ?, ?)",
                ("book_copy_created", cur2.lastrowid, book.title.strip(), now_iso()),
            )
        return {"ok": True, "book_id": book_id, "copy_id": cur2.lastrowid, "barcode": barcode}
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=f"Book/copy already exists or barcode is duplicated: {exc}")


@app.get("/api/books")
def list_books():
    with db() as conn:
        rows = conn.execute(
            """
            SELECT b.id AS book_id, b.title, b.author, b.isbn, b.cover_url,
                   bc.id AS copy_id, bc.barcode, bc.status,
                   c.name AS borrowed_by, l.due_at
            FROM book_copies bc
            JOIN books b ON b.id = bc.book_id
            LEFT JOIN loans l ON l.book_copy_id = bc.id AND l.status = 'active'
            LEFT JOIN children c ON c.id = l.child_id
            ORDER BY b.title COLLATE NOCASE
            """
        ).fetchall()
    return rows_to_dicts(rows)


def resolve_book_copy(conn: sqlite3.Connection, code: str):
    code = code.strip()
    row = conn.execute(
        """
        SELECT bc.*, b.title, b.author, b.isbn
        FROM book_copies bc
        JOIN books b ON b.id = bc.book_id
        WHERE bc.barcode = ?
        """,
        (code,),
    ).fetchone()
    if row:
        return row

    # ISBN fallback: find the first copy whose parent book has this ISBN
    row = conn.execute(
        """
        SELECT bc.*, b.title, b.author, b.isbn
        FROM book_copies bc
        JOIN books b ON b.id = bc.book_id
        WHERE b.isbn = ?
        ORDER BY bc.id
        LIMIT 1
        """,
        (code,),
    ).fetchone()
    return row


@app.post("/api/checkout")
def checkout(payload: CheckoutIn):
    with db() as conn:
        child = conn.execute(
            "SELECT * FROM children WHERE barcode = ? AND active = 1",
            (payload.child_barcode.strip(),),
        ).fetchone()
        if not child:
            raise HTTPException(status_code=404, detail="Child card not found")

        active_count = conn.execute(
            "SELECT COUNT(*) AS count FROM loans WHERE child_id = ? AND status = 'active'",
            (child["id"],),
        ).fetchone()["count"]
        if active_count >= child["borrow_limit"]:
            raise HTTPException(status_code=409, detail=f"Borrow limit reached for {child['name']}")

        copy = resolve_book_copy(conn, payload.book_code)
        if not copy:
            raise HTTPException(status_code=404, detail="Book not found. Add it in Admin first.")

        active_loan = conn.execute(
            "SELECT id FROM loans WHERE book_copy_id = ? AND status = 'active'",
            (copy["id"],),
        ).fetchone()
        if active_loan:
            raise HTTPException(status_code=409, detail="This book is already borrowed")

        borrowed_at = datetime.now(timezone.utc)
        due_at = borrowed_at + timedelta(days=DEFAULT_LOAN_DAYS)
        cur = conn.execute(
            """
            INSERT INTO loans(book_copy_id, child_id, borrowed_at, due_at, status)
            VALUES (?, ?, ?, ?, 'active')
            """,
            (copy["id"], child["id"], borrowed_at.isoformat(), due_at.isoformat()),
        )
        conn.execute("UPDATE book_copies SET status = 'borrowed' WHERE id = ?", (copy["id"],))
        conn.execute(
            "INSERT INTO events(event_type, child_id, book_copy_id, notes, created_at) VALUES (?, ?, ?, ?, ?)",
            ("checkout", child["id"], copy["id"], copy["title"], now_iso()),
        )

    return {
        "ok": True,
        "loan_id": cur.lastrowid,
        "child": child["name"],
        "title": copy["title"],
        "due_at": due_at.date().isoformat(),
    }


@app.post("/api/return")
def return_book(payload: ReturnIn):
    with db() as conn:
        copy = resolve_book_copy(conn, payload.book_code)
        if not copy:
            raise HTTPException(status_code=404, detail="Book not found")

        loan = conn.execute(
            """
            SELECT l.*, c.name AS child_name
            FROM loans l
            JOIN children c ON c.id = l.child_id
            WHERE l.book_copy_id = ? AND l.status = 'active'
            """,
            (copy["id"],),
        ).fetchone()
        if not loan:
            raise HTTPException(status_code=409, detail="This book is not currently borrowed")

        conn.execute(
            "UPDATE loans SET returned_at = ?, status = 'returned' WHERE id = ?",
            (now_iso(), loan["id"]),
        )
        conn.execute("UPDATE book_copies SET status = 'available' WHERE id = ?", (copy["id"],))
        conn.execute(
            "INSERT INTO events(event_type, child_id, book_copy_id, notes, created_at) VALUES (?, ?, ?, ?, ?)",
            ("return", loan["child_id"], copy["id"], copy["title"], now_iso()),
        )

    return {"ok": True, "title": copy["title"], "returned_from": loan["child_name"]}


@app.get("/api/loans")
def list_loans():
    with db() as conn:
        rows = conn.execute(
            """
            SELECT l.id, c.name AS child, b.title, b.author, bc.barcode, l.borrowed_at, l.due_at, l.status
            FROM loans l
            JOIN children c ON c.id = l.child_id
            JOIN book_copies bc ON bc.id = l.book_copy_id
            JOIN books b ON b.id = bc.book_id
            WHERE l.status = 'active'
            ORDER BY l.due_at ASC
            """
        ).fetchall()
    return rows_to_dicts(rows)
