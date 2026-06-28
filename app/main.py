import os
import sqlite3
import urllib.parse
import urllib.request
import json
import base64
import binascii
import mimetypes
import uuid
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

DB_PATH = os.getenv("LIBRARY_DB", "/data/library.db")
DEFAULT_LOAN_DAYS = int(os.getenv("DEFAULT_LOAN_DAYS", "7"))
APP_DIR = Path(__file__).resolve().parent
APP_VERSION = "0.2.1"
COVERS_DIR = Path(os.getenv("COVERS_DIR", "/data/covers"))
CHILDREN_DIR = Path(os.getenv("CHILDREN_DIR", "/data/children"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Letmein!2")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN") or secrets.token_urlsafe(32)
COVERS_DIR.mkdir(parents=True, exist_ok=True)
CHILDREN_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ShelfQuest", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
app.mount("/covers", StaticFiles(directory=str(COVERS_DIR)), name="covers")
app.mount("/children", StaticFiles(directory=str(CHILDREN_DIR)), name="children")


COPY_STATUSES = {"available", "borrowed", "deleted"}
CONDITION_STATUSES = {"good", "damaged_needs_repair"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def db() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, sql: str):
    existing_cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing_cols:
        conn.execute(sql)


def init_db():
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS children (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                barcode TEXT NOT NULL UNIQUE,
                borrow_limit INTEGER NOT NULL DEFAULT 5,
                photo_url TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                isbn TEXT UNIQUE,
                title TEXT NOT NULL,
                author TEXT,
                illustrator TEXT,
                synopsis TEXT,
                cover_url TEXT,
                category TEXT,
                reading_level TEXT,
                owned_qty INTEGER NOT NULL DEFAULT 1,
                deleted_at TEXT,
                updated_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS book_copies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                barcode TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'available',
                condition_status TEXT NOT NULL DEFAULT 'good',
                shelf_location TEXT,
                condition_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
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

        # Lightweight migrations for databases created by earlier ShelfQuest versions.
        add_column_if_missing(conn, "books", "illustrator", "ALTER TABLE books ADD COLUMN illustrator TEXT")
        add_column_if_missing(conn, "books", "synopsis", "ALTER TABLE books ADD COLUMN synopsis TEXT")
        add_column_if_missing(conn, "books", "owned_qty", "ALTER TABLE books ADD COLUMN owned_qty INTEGER NOT NULL DEFAULT 1")
        add_column_if_missing(conn, "books", "deleted_at", "ALTER TABLE books ADD COLUMN deleted_at TEXT")
        add_column_if_missing(conn, "books", "updated_at", "ALTER TABLE books ADD COLUMN updated_at TEXT")
        add_column_if_missing(conn, "book_copies", "condition_status", "ALTER TABLE book_copies ADD COLUMN condition_status TEXT NOT NULL DEFAULT 'good'")
        add_column_if_missing(conn, "book_copies", "updated_at", "ALTER TABLE book_copies ADD COLUMN updated_at TEXT")
        add_column_if_missing(conn, "children", "photo_url", "ALTER TABLE children ADD COLUMN photo_url TEXT")
        add_column_if_missing(conn, "children", "updated_at", "ALTER TABLE children ADD COLUMN updated_at TEXT")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def root():
    return FileResponse(str(APP_DIR / "static" / "index.html"))


class AdminLoginIn(BaseModel):
    password: str = Field(min_length=1)


class ChildIn(BaseModel):
    name: str = Field(min_length=1)
    barcode: str = Field(min_length=1)
    borrow_limit: int = Field(default=5, ge=1, le=50)


class ChildUpdateIn(BaseModel):
    name: str = Field(min_length=1)
    barcode: str = Field(min_length=1)
    borrow_limit: int = Field(default=5, ge=1, le=50)
    active: int = Field(default=1, ge=0, le=1)


class BookIn(BaseModel):
    isbn: Optional[str] = None
    title: str = Field(min_length=1)
    author: Optional[str] = None
    illustrator: Optional[str] = None
    synopsis: Optional[str] = None
    cover_url: Optional[str] = None
    category: Optional[str] = None
    reading_level: Optional[str] = None
    owned_qty: int = Field(default=1, ge=1, le=500)
    barcode: Optional[str] = None


class BookUpdateIn(BaseModel):
    copy_id: Optional[int] = None
    isbn: Optional[str] = None
    title: str = Field(min_length=1)
    author: Optional[str] = None
    illustrator: Optional[str] = None
    synopsis: Optional[str] = None
    cover_url: Optional[str] = None
    category: Optional[str] = None
    reading_level: Optional[str] = None
    owned_qty: int = Field(default=1, ge=1, le=500)
    barcode: Optional[str] = None
    condition_status: str = "good"
    condition_note: Optional[str] = None
    shelf_location: Optional[str] = None


class ConditionUpdateIn(BaseModel):
    condition_status: str = Field(min_length=1)
    condition_note: Optional[str] = None


class CoverUploadIn(BaseModel):
    filename: str = Field(min_length=1)
    content_type: Optional[str] = None
    data_base64: str = Field(min_length=1)


class CheckoutIn(BaseModel):
    child_barcode: str
    book_code: str


class ReturnIn(BaseModel):
    book_code: str


class BulkReturnIn(BaseModel):
    book_codes: list[str] = Field(default_factory=list)


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


def clean_optional(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def validate_condition_status(value: str) -> str:
    value = (value or "good").strip()
    if value not in CONDITION_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid condition status: {value}")
    return value


def cover_extension(filename: str, content_type: Optional[str] = None) -> str:
    name = (filename or "cover").lower().strip()
    ext = Path(name).suffix.lower()
    allowed = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    if ext in allowed:
        return ".jpg" if ext == ".jpeg" else ext
    guessed = mimetypes.guess_extension((content_type or "").split(";")[0].strip())
    if guessed in allowed:
        return ".jpg" if guessed == ".jpeg" else guessed
    return ".jpg"


def save_cover_bytes(book_id: int, raw: bytes, filename: str, content_type: Optional[str] = None) -> str:
    if not raw:
        raise HTTPException(status_code=400, detail="Cover file is empty")
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Cover file is too large. Keep it under 8 MB.")
    ext = cover_extension(filename, content_type)
    out_name = f"book-{book_id}-{uuid.uuid4().hex[:12]}{ext}"
    out_path = COVERS_DIR / out_name
    out_path.write_bytes(raw)
    return f"/covers/{out_name}"


def save_child_photo_bytes(child_id: int, raw: bytes, filename: str, content_type: Optional[str] = None) -> str:
    if not raw:
        raise HTTPException(status_code=400, detail="Photo file is empty")
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Photo file is too large. Keep it under 8 MB.")
    ext = cover_extension(filename, content_type)
    out_name = f"child-{child_id}-{uuid.uuid4().hex[:12]}{ext}"
    out_path = CHILDREN_DIR / out_name
    out_path.write_bytes(raw)
    return f"/children/{out_name}"


def download_cover(url: str, book_id: int) -> Optional[str]:
    parsed = urllib.parse.urlparse(url or "")
    if parsed.scheme not in {"http", "https"}:
        return None
    req = urllib.request.Request(url, headers={"User-Agent": "ShelfQuest/0.1.7"})
    with urllib.request.urlopen(req, timeout=12) as resp:
        content_type = resp.headers.get("content-type")
        raw = resp.read(8 * 1024 * 1024 + 1)
    return save_cover_bytes(book_id, raw, Path(parsed.path).name or f"book-{book_id}", content_type)


def require_admin(x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token")):
    if not x_admin_token or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Admin password required")
    return True


@app.post("/api/admin/login")
def admin_login(payload: AdminLoginIn):
    if not secrets.compare_digest(payload.password, ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="Incorrect admin password")
    return {"ok": True, "token": ADMIN_TOKEN}


@app.get("/api/health")
def health():
    return {"ok": True, "db": DB_PATH, "version": APP_VERSION}


@app.post("/api/children")
def add_child(child: ChildIn, _admin: bool = Depends(require_admin)):
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


@app.put("/api/children/{child_id}")
def update_child(child_id: int, payload: ChildUpdateIn, _admin: bool = Depends(require_admin)):
    try:
        with db() as conn:
            child = conn.execute("SELECT * FROM children WHERE id = ?", (child_id,)).fetchone()
            if not child:
                raise HTTPException(status_code=404, detail="Child not found")
            conflict = conn.execute("SELECT id FROM children WHERE barcode = ? AND id != ?", (payload.barcode.strip(), child_id)).fetchone()
            if conflict:
                raise HTTPException(status_code=409, detail="Another child already has that barcode")
            conn.execute(
                "UPDATE children SET name = ?, barcode = ?, borrow_limit = ?, active = ?, updated_at = ? WHERE id = ?",
                (payload.name.strip(), payload.barcode.strip(), payload.borrow_limit, payload.active, now_iso(), child_id),
            )
            conn.execute(
                "INSERT INTO events(event_type, child_id, notes, created_at) VALUES (?, ?, ?, ?)",
                ("child_updated", child_id, payload.name.strip(), now_iso()),
            )
        return {"ok": True, "child_id": child_id}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Child barcode already exists")


@app.post("/api/children/{child_id}/photo")
def upload_child_photo(child_id: int, payload: CoverUploadIn, _admin: bool = Depends(require_admin)):
    try:
        raw = base64.b64decode(payload.data_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Invalid base64 photo data")

    with db() as conn:
        child = conn.execute("SELECT id, name FROM children WHERE id = ?", (child_id,)).fetchone()
        if not child:
            raise HTTPException(status_code=404, detail="Child not found")
        photo_url = save_child_photo_bytes(child_id, raw, payload.filename, payload.content_type)
        conn.execute("UPDATE children SET photo_url = ?, updated_at = ? WHERE id = ?", (photo_url, now_iso(), child_id))
        conn.execute(
            "INSERT INTO events(event_type, child_id, notes, created_at) VALUES (?, ?, ?, ?)",
            ("child_photo_uploaded", child_id, photo_url, now_iso()),
        )
    return {"ok": True, "child_id": child_id, "photo_url": photo_url}


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


def create_or_update_book_and_copy(conn: sqlite3.Connection, book: BookIn):
    isbn = clean_optional(book.isbn)
    barcode = clean_optional(book.barcode) or isbn
    if not barcode:
        raise HTTPException(status_code=400, detail="A barcode or ISBN is required")

    existing = conn.execute("SELECT id FROM books WHERE isbn = ? AND deleted_at IS NULL", (isbn,)).fetchone() if isbn else None
    if existing:
        book_id = existing["id"]
        conn.execute(
            """
            UPDATE books
            SET title = CASE WHEN title IS NULL OR title = '' OR title LIKE 'Unknown title (%' THEN ? ELSE title END,
                author = CASE WHEN (author IS NULL OR author = '') AND ? != '' THEN ? ELSE author END,
                illustrator = CASE WHEN (illustrator IS NULL OR illustrator = '') AND ? != '' THEN ? ELSE illustrator END,
                synopsis = CASE WHEN (synopsis IS NULL OR synopsis = '') AND ? != '' THEN ? ELSE synopsis END,
                cover_url = CASE WHEN (cover_url IS NULL OR cover_url = '') AND ? != '' THEN ? ELSE cover_url END,
                category = CASE WHEN (category IS NULL OR category = '') AND ? != '' THEN ? ELSE category END,
                owned_qty = CASE WHEN owned_qty < ? THEN ? ELSE owned_qty END,
                updated_at = ?
            WHERE id = ?
            """,
            (
                book.title.strip(),
                (book.author or '').strip(), (book.author or '').strip(),
                (book.illustrator or '').strip(), (book.illustrator or '').strip(),
                (book.synopsis or '').strip(), (book.synopsis or '').strip(),
                (book.cover_url or '').strip(), (book.cover_url or '').strip(),
                (book.category or '').strip(), (book.category or '').strip(),
                book.owned_qty, book.owned_qty,
                now_iso(),
                book_id,
            ),
        )
    else:
        cur = conn.execute(
            """
            INSERT INTO books(isbn, title, author, illustrator, synopsis, cover_url, category, reading_level, owned_qty, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                isbn,
                book.title.strip(),
                clean_optional(book.author),
                clean_optional(book.illustrator),
                clean_optional(book.synopsis),
                clean_optional(book.cover_url),
                clean_optional(book.category),
                clean_optional(book.reading_level),
                book.owned_qty,
                now_iso(),
                now_iso(),
            ),
        )
        book_id = cur.lastrowid

    # Copy-barcode handling:
    # - If the target barcode already exists for this book, reuse that copy.
    # - If an ISBN-only temporary copy exists and the new barcode is different,
    #   relabel that copy instead of creating a duplicate.
    # - Otherwise create a new scannable copy.
    existing_target = conn.execute(
        "SELECT id, book_id FROM book_copies WHERE barcode = ? AND status != 'deleted'",
        (barcode,),
    ).fetchone()
    if existing_target:
        if existing_target["book_id"] != book_id:
            raise sqlite3.IntegrityError("barcode belongs to another book")
        copy_id = existing_target["id"]
    else:
        isbn_copy = None
        if isbn and barcode != isbn:
            isbn_copy = conn.execute(
                "SELECT id FROM book_copies WHERE book_id = ? AND barcode = ? AND status != 'deleted'",
                (book_id, isbn),
            ).fetchone()
        if isbn_copy:
            conn.execute("UPDATE book_copies SET barcode = ?, updated_at = ? WHERE id = ?", (barcode, now_iso(), isbn_copy["id"]))
            copy_id = isbn_copy["id"]
            conn.execute(
                "INSERT INTO events(event_type, book_copy_id, notes, created_at) VALUES (?, ?, ?, ?)",
                ("book_copy_relabelled", copy_id, f"{isbn} -> {barcode}", now_iso()),
            )
        else:
            cur2 = conn.execute(
                "INSERT INTO book_copies(book_id, barcode, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (book_id, barcode, now_iso(), now_iso()),
            )
            copy_id = cur2.lastrowid
            conn.execute(
                "INSERT INTO events(event_type, book_copy_id, notes, created_at) VALUES (?, ?, ?, ?)",
                ("book_copy_created", copy_id, book.title.strip(), now_iso()),
            )
    return book_id, copy_id, barcode


@app.post("/api/books")
def add_book(book: BookIn, _admin: bool = Depends(require_admin)):
    try:
        with db() as conn:
            book_id, copy_id, barcode = create_or_update_book_and_copy(conn, book)
        return {"ok": True, "book_id": book_id, "copy_id": copy_id, "barcode": barcode}
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=f"Book/copy already exists or barcode is duplicated: {exc}")


@app.get("/api/books")
def list_books(q: Optional[str] = Query(default=None)):
    q_clean = (q or "").strip().lower()
    with db() as conn:
        if q_clean:
            like = f"%{q_clean}%"
            rows = conn.execute(
                """
                SELECT b.id AS book_id, b.title, b.author, b.illustrator, b.synopsis, b.isbn,
                       b.cover_url, b.category, b.reading_level, b.owned_qty,
                       bc.id AS copy_id, bc.barcode, bc.status, bc.condition_status, bc.condition_note, bc.shelf_location,
                       c.name AS borrowed_by, l.due_at
                FROM book_copies bc
                JOIN books b ON b.id = bc.book_id
                LEFT JOIN loans l ON l.book_copy_id = bc.id AND l.status = 'active'
                LEFT JOIN children c ON c.id = l.child_id
                WHERE b.deleted_at IS NULL
                  AND bc.status != 'deleted'
                  AND lower(
                    coalesce(b.title,'') || ' ' || coalesce(b.author,'') || ' ' || coalesce(b.illustrator,'') || ' ' ||
                    coalesce(b.synopsis,'') || ' ' || coalesce(b.isbn,'') || ' ' || coalesce(b.category,'') || ' ' ||
                    coalesce(b.reading_level,'') || ' ' || coalesce(b.cover_url,'') || ' ' || coalesce(bc.barcode,'') || ' ' ||
                    coalesce(bc.status,'') || ' ' || coalesce(bc.condition_status,'') || ' ' || coalesce(bc.condition_note,'') || ' ' ||
                    coalesce(bc.shelf_location,'') || ' ' || coalesce(c.name,'')
                  ) LIKE ?
                ORDER BY b.title COLLATE NOCASE
                """,
                (like,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT b.id AS book_id, b.title, b.author, b.illustrator, b.synopsis, b.isbn,
                       b.cover_url, b.category, b.reading_level, b.owned_qty,
                       bc.id AS copy_id, bc.barcode, bc.status, bc.condition_status, bc.condition_note, bc.shelf_location,
                       c.name AS borrowed_by, l.due_at
                FROM book_copies bc
                JOIN books b ON b.id = bc.book_id
                LEFT JOIN loans l ON l.book_copy_id = bc.id AND l.status = 'active'
                LEFT JOIN children c ON c.id = l.child_id
                WHERE b.deleted_at IS NULL
                  AND bc.status != 'deleted'
                ORDER BY b.title COLLATE NOCASE
                """
            ).fetchall()
    return rows_to_dicts(rows)


@app.put("/api/books/{book_id}")
def update_book(book_id: int, payload: BookUpdateIn, _admin: bool = Depends(require_admin)):
    condition_status = validate_condition_status(payload.condition_status)
    isbn = clean_optional(payload.isbn)
    barcode = clean_optional(payload.barcode)
    copy_id = payload.copy_id

    try:
        with db() as conn:
            book = conn.execute("SELECT * FROM books WHERE id = ? AND deleted_at IS NULL", (book_id,)).fetchone()
            if not book:
                raise HTTPException(status_code=404, detail="Book not found")

            if copy_id is None:
                copy = conn.execute(
                    "SELECT * FROM book_copies WHERE book_id = ? AND status != 'deleted' ORDER BY id LIMIT 1",
                    (book_id,),
                ).fetchone()
            else:
                copy = conn.execute(
                    "SELECT * FROM book_copies WHERE id = ? AND book_id = ? AND status != 'deleted'",
                    (copy_id, book_id),
                ).fetchone()
            if not copy:
                raise HTTPException(status_code=404, detail="Book copy not found")

            if isbn and isbn != book["isbn"]:
                conflict = conn.execute("SELECT id FROM books WHERE isbn = ? AND id != ? AND deleted_at IS NULL", (isbn, book_id)).fetchone()
                if conflict:
                    raise HTTPException(status_code=409, detail="Another book already has this ISBN")

            if barcode and barcode != copy["barcode"]:
                conflict = conn.execute("SELECT id FROM book_copies WHERE barcode = ? AND id != ? AND status != 'deleted'", (barcode, copy["id"])).fetchone()
                if conflict:
                    raise HTTPException(status_code=409, detail="Another book copy already has this barcode")

            conn.execute(
                """
                UPDATE books
                SET isbn = ?, title = ?, author = ?, illustrator = ?, synopsis = ?, cover_url = ?,
                    category = ?, reading_level = ?, owned_qty = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    isbn,
                    payload.title.strip(),
                    clean_optional(payload.author),
                    clean_optional(payload.illustrator),
                    clean_optional(payload.synopsis),
                    clean_optional(payload.cover_url),
                    clean_optional(payload.category),
                    clean_optional(payload.reading_level),
                    payload.owned_qty,
                    now_iso(),
                    book_id,
                ),
            )
            conn.execute(
                """
                UPDATE book_copies
                SET barcode = ?, condition_status = ?, condition_note = ?, shelf_location = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    barcode or copy["barcode"],
                    condition_status,
                    clean_optional(payload.condition_note),
                    clean_optional(payload.shelf_location),
                    now_iso(),
                    copy["id"],
                ),
            )
            conn.execute(
                "INSERT INTO events(event_type, book_copy_id, notes, created_at) VALUES (?, ?, ?, ?)",
                ("book_updated", copy["id"], payload.title.strip(), now_iso()),
            )
        return {"ok": True, "book_id": book_id, "copy_id": copy["id"]}
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=f"Could not update book: {exc}")


@app.patch("/api/book-copies/{copy_id}/condition")
def update_copy_condition(copy_id: int, payload: ConditionUpdateIn, _admin: bool = Depends(require_admin)):
    condition_status = validate_condition_status(payload.condition_status)
    with db() as conn:
        copy = conn.execute(
            """
            SELECT bc.*, b.title
            FROM book_copies bc
            JOIN books b ON b.id = bc.book_id
            WHERE bc.id = ? AND b.deleted_at IS NULL AND bc.status != 'deleted'
            """,
            (copy_id,),
        ).fetchone()
        if not copy:
            raise HTTPException(status_code=404, detail="Book copy not found")
        conn.execute(
            "UPDATE book_copies SET condition_status = ?, condition_note = ?, updated_at = ? WHERE id = ?",
            (condition_status, clean_optional(payload.condition_note), now_iso(), copy_id),
        )
        conn.execute(
            "INSERT INTO events(event_type, book_copy_id, notes, created_at) VALUES (?, ?, ?, ?)",
            ("condition_updated", copy_id, f"{copy['title']}: {condition_status}", now_iso()),
        )
    return {"ok": True, "copy_id": copy_id, "condition_status": condition_status}


@app.delete("/api/books/{book_id}")
def delete_book(book_id: int, _admin: bool = Depends(require_admin)):
    with db() as conn:
        book = conn.execute("SELECT * FROM books WHERE id = ? AND deleted_at IS NULL", (book_id,)).fetchone()
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")

        active = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM loans l
            JOIN book_copies bc ON bc.id = l.book_copy_id
            WHERE bc.book_id = ? AND l.status = 'active'
            """,
            (book_id,),
        ).fetchone()["count"]
        if active:
            raise HTTPException(status_code=409, detail="Cannot delete a book while it is currently borrowed")

        conn.execute("UPDATE books SET deleted_at = ?, updated_at = ? WHERE id = ?", (now_iso(), now_iso(), book_id))
        conn.execute("UPDATE book_copies SET status = 'deleted', updated_at = ? WHERE book_id = ?", (now_iso(), book_id))
        conn.execute(
            "INSERT INTO events(event_type, notes, created_at) VALUES (?, ?, ?)",
            ("book_deleted", book["title"], now_iso()),
        )
    return {"ok": True, "book_id": book_id, "title": book["title"]}


@app.post("/api/books/{book_id}/cover")
def upload_book_cover(book_id: int, payload: CoverUploadIn, _admin: bool = Depends(require_admin)):
    try:
        raw = base64.b64decode(payload.data_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Invalid base64 cover data")

    with db() as conn:
        book = conn.execute("SELECT id, title FROM books WHERE id = ? AND deleted_at IS NULL", (book_id,)).fetchone()
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")
        cover_url = save_cover_bytes(book_id, raw, payload.filename, payload.content_type)
        conn.execute("UPDATE books SET cover_url = ?, updated_at = ? WHERE id = ?", (cover_url, now_iso(), book_id))
        conn.execute(
            "INSERT INTO events(event_type, notes, created_at) VALUES (?, ?, ?)",
            ("cover_uploaded", f"{book['title']}: {cover_url}", now_iso()),
        )
    return {"ok": True, "book_id": book_id, "cover_url": cover_url}


@app.post("/api/covers/cache")
def cache_remote_covers(_admin: bool = Depends(require_admin)):
    cached = 0
    skipped = 0
    failed = []
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, title, cover_url
            FROM books
            WHERE deleted_at IS NULL
              AND cover_url IS NOT NULL
              AND trim(cover_url) != ''
              AND lower(cover_url) NOT LIKE '/covers/%'
            ORDER BY title COLLATE NOCASE
            """
        ).fetchall()
        for row in rows:
            url = (row["cover_url"] or "").strip()
            if not url.lower().startswith(("http://", "https://")):
                skipped += 1
                continue
            try:
                local_url = download_cover(url, row["id"])
                if not local_url:
                    skipped += 1
                    continue
                conn.execute("UPDATE books SET cover_url = ?, updated_at = ? WHERE id = ?", (local_url, now_iso(), row["id"]))
                cached += 1
            except Exception as exc:
                failed.append({"book_id": row["id"], "title": row["title"], "error": str(exc)[:180]})
        conn.execute(
            "INSERT INTO events(event_type, notes, created_at) VALUES (?, ?, ?)",
            ("covers_cached", f"cached={cached}, skipped={skipped}, failed={len(failed)}", now_iso()),
        )
    return {"ok": True, "cached": cached, "skipped": skipped, "failed": failed[:20], "failed_count": len(failed)}


def resolve_book_copy(conn: sqlite3.Connection, code: str):
    code = code.strip()
    row = conn.execute(
        """
        SELECT bc.*, b.title, b.author, b.isbn
        FROM book_copies bc
        JOIN books b ON b.id = bc.book_id
        WHERE bc.barcode = ?
          AND b.deleted_at IS NULL
          AND bc.status != 'deleted'
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
          AND b.deleted_at IS NULL
          AND bc.status != 'deleted'
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

        if copy["condition_status"] == "damaged_needs_repair":
            raise HTTPException(status_code=409, detail="This book is marked 'Damaged, needs repair' and cannot be borrowed yet")

        if copy["status"] != "available":
            if copy["status"] == "borrowed":
                raise HTTPException(status_code=409, detail="This book is already borrowed")
            raise HTTPException(status_code=409, detail=f"This book is not available: {copy['status']}")

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
        conn.execute("UPDATE book_copies SET status = 'borrowed', updated_at = ? WHERE id = ?", (now_iso(), copy["id"]))
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


def return_one_book(conn: sqlite3.Connection, book_code: str):
    copy = resolve_book_copy(conn, book_code)
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
    conn.execute("UPDATE book_copies SET status = 'available', updated_at = ? WHERE id = ?", (now_iso(), copy["id"]))
    conn.execute(
        "INSERT INTO events(event_type, child_id, book_copy_id, notes, created_at) VALUES (?, ?, ?, ?, ?)",
        ("return", loan["child_id"], copy["id"], copy["title"], now_iso()),
    )
    return {"ok": True, "title": copy["title"], "returned_from": loan["child_name"], "book_code": book_code.strip()}


@app.post("/api/return")
def return_book(payload: ReturnIn):
    with db() as conn:
        return return_one_book(conn, payload.book_code)


@app.post("/api/returns/bulk")
def bulk_return_books(payload: BulkReturnIn, _admin: bool = Depends(require_admin)):
    returned = []
    failed = []
    seen = set()
    codes = [str(code or "").strip() for code in payload.book_codes]
    codes = [code for code in codes if code]
    if not codes:
        raise HTTPException(status_code=400, detail="No book barcodes supplied")

    with db() as conn:
        for code in codes:
            if code in seen:
                continue
            seen.add(code)
            try:
                returned.append(return_one_book(conn, code))
            except HTTPException as exc:
                failed.append({"book_code": code, "error": exc.detail})
            except Exception as exc:
                failed.append({"book_code": code, "error": str(exc)[:180]})

        conn.execute(
            "INSERT INTO events(event_type, notes, created_at) VALUES (?, ?, ?)",
            ("bulk_return", f"returned={len(returned)}, failed={len(failed)}", now_iso()),
        )

    return {"ok": True, "returned": returned, "failed": failed}


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
              AND b.deleted_at IS NULL
              AND bc.status != 'deleted'
            ORDER BY l.due_at ASC
            """
        ).fetchall()
    return rows_to_dicts(rows)
