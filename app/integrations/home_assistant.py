from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI

from app.main import APP_VERSION, db, now_iso


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return slug or fallback


def _due_label(due_at: str | None, now: datetime) -> str:
    due_dt = _parse_datetime(due_at)
    if due_dt is None:
        return "no due date"

    days_until_due = (due_dt.date() - now.date()).days
    due_date = due_dt.date().isoformat()

    if due_dt < now:
        return f"overdue since {due_date}"
    if days_until_due == 0:
        return "due today"
    if days_until_due == 1:
        return "due tomorrow"
    return f"due {due_date}"


def _book_payload(row: sqlite3.Row, now: datetime) -> dict[str, Any]:
    due_dt = _parse_datetime(row["due_at"])
    days_until_due = (due_dt.date() - now.date()).days if due_dt else None
    is_overdue = bool(due_dt and due_dt < now)

    return {
        "loan_id": row["loan_id"],
        "book_id": row["book_id"],
        "copy_id": row["copy_id"],
        "title": row["title"],
        "author": row["author"],
        "isbn": row["isbn"],
        "barcode": row["barcode"],
        "cover_url": row["cover_url"],
        "category": row["category"],
        "borrowed_at": row["borrowed_at"],
        "due_at": row["due_at"],
        "due_date": due_dt.date().isoformat() if due_dt else None,
        "days_until_due": days_until_due,
        "is_overdue": is_overdue,
        "due_label": _due_label(row["due_at"], now),
    }


def _child_summary(active_loans: int, overdue_loans: int, next_due_at: str | None) -> str:
    if active_loans == 0:
        return "No borrowed books"
    book_word = "book" if active_loans == 1 else "books"
    if overdue_loans:
        overdue_word = "book" if overdue_loans == 1 else "books"
        return f"{active_loans} {book_word}, {overdue_loans} overdue {overdue_word}"
    if next_due_at:
        due_dt = _parse_datetime(next_due_at)
        if due_dt:
            return f"{active_loans} {book_word}, next due {due_dt.date().isoformat()}"
    return f"{active_loans} {book_word}"


def _child_markdown(books: list[dict[str, Any]]) -> str:
    if not books:
        return "_No books currently borrowed._"

    lines = []
    for book in books:
        title = book.get("title") or "Untitled book"
        author = book.get("author")
        due_label = book.get("due_label") or "no due date"
        author_text = f" by {author}" if author else ""
        lines.append(f"- **{title}**{author_text} — {due_label}")
    return "\n".join(lines)


def _empty_child(row: sqlite3.Row, slug: str) -> dict[str, Any]:
    return {
        "id": row["child_id"],
        "name": row["child_name"],
        "slug": slug,
        "photo_url": row["photo_url"],
        "borrow_limit": row["borrow_limit"],
        "active_loans": 0,
        "overdue_loans": 0,
        "next_due_at": None,
        "next_due_date": None,
        "summary": "No borrowed books",
        "markdown": "_No books currently borrowed._",
        "books": [],
    }


def _library_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "total_titles": conn.execute("SELECT COUNT(*) FROM books WHERE deleted_at IS NULL").fetchone()[0],
        "total_copies": conn.execute("SELECT COUNT(*) FROM book_copies WHERE status != 'deleted'").fetchone()[0],
        "available_copies": conn.execute("SELECT COUNT(*) FROM book_copies WHERE status = 'available'").fetchone()[0],
        "borrowed_copies": conn.execute("SELECT COUNT(*) FROM book_copies WHERE status = 'borrowed'").fetchone()[0],
        "damaged_copies": conn.execute(
            """
            SELECT COUNT(*)
            FROM book_copies
            WHERE status != 'deleted'
              AND condition_status = 'damaged_needs_repair'
            """
        ).fetchone()[0],
    }


def build_home_assistant_reading_payload() -> dict[str, Any]:
    now = datetime.now(timezone.utc)

    with db() as conn:
        counts = _library_counts(conn)
        rows = conn.execute(
            """
            SELECT c.id AS child_id,
                   c.name AS child_name,
                   c.photo_url,
                   c.borrow_limit,
                   l.id AS loan_id,
                   l.borrowed_at,
                   l.due_at,
                   bc.id AS copy_id,
                   bc.barcode,
                   b.id AS book_id,
                   b.title,
                   b.author,
                   b.isbn,
                   b.cover_url,
                   b.category
            FROM children c
            LEFT JOIN loans l ON l.child_id = c.id AND l.status = 'active'
            LEFT JOIN book_copies bc ON bc.id = l.book_copy_id AND bc.status != 'deleted'
            LEFT JOIN books b ON b.id = bc.book_id AND b.deleted_at IS NULL
            WHERE c.active = 1
            ORDER BY c.name COLLATE NOCASE, l.due_at ASC, b.title COLLATE NOCASE
            """
        ).fetchall()

    children_by_id: dict[int, dict[str, Any]] = {}
    used_slugs: set[str] = set()

    for row in rows:
        child_id = row["child_id"]
        if child_id not in children_by_id:
            base_slug = _slugify(row["child_name"], f"child_{child_id}")
            slug = base_slug
            if slug in used_slugs:
                slug = f"{base_slug}_{child_id}"
            used_slugs.add(slug)
            children_by_id[child_id] = _empty_child(row, slug)

        if row["loan_id"] is None or row["book_id"] is None:
            continue

        children_by_id[child_id]["books"].append(_book_payload(row, now))

    total_active_loans = 0
    total_overdue_loans = 0
    children = list(children_by_id.values())

    for child in children:
        books = child["books"]
        active_loans = len(books)
        overdue_loans = sum(1 for book in books if book["is_overdue"])
        next_due_at = books[0]["due_at"] if books else None
        next_due_dt = _parse_datetime(next_due_at)

        child["active_loans"] = active_loans
        child["overdue_loans"] = overdue_loans
        child["next_due_at"] = next_due_at
        child["next_due_date"] = next_due_dt.date().isoformat() if next_due_dt else None
        child["summary"] = _child_summary(active_loans, overdue_loans, next_due_at)
        child["markdown"] = _child_markdown(books)

        total_active_loans += active_loans
        total_overdue_loans += overdue_loans

    return {
        "ok": True,
        "version": APP_VERSION,
        "generated_at": now_iso(),
        **counts,
        "total_children": len(children),
        "total_active_loans": total_active_loans,
        "overdue_loans": total_overdue_loans,
        "children": children,
        "children_by_slug": {child["slug"]: child for child in children},
    }


def register_home_assistant_routes(app: FastAPI) -> None:
    @app.get("/api/integrations/home-assistant/reading")
    def home_assistant_reading_status():
        return build_home_assistant_reading_payload()
