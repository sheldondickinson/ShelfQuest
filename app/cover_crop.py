import base64
import binascii
import os
import uuid
from io import BytesIO
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import BackgroundTasks, Depends, HTTPException
from PIL import Image, ImageOps


AUTO_CROP_ENABLED = os.getenv("AUTO_CROP_COVER_PHOTOS", "true").strip().lower() not in {"0", "false", "no", "off"}
AUTO_CROP_INSET_FRACTION = float(os.getenv("AUTO_CROP_INSET_FRACTION", "0.025"))
AUTO_CROP_MAX_DIMENSION = int(os.getenv("AUTO_CROP_MAX_DIMENSION", "1600"))
AUTO_CROP_JPEG_QUALITY = int(os.getenv("AUTO_CROP_JPEG_QUALITY", "88"))


def _image_to_bgr(raw: bytes) -> Optional[np.ndarray]:
    """Decode image bytes using Pillow so iPhone EXIF orientation is respected."""
    try:
        with Image.open(BytesIO(raw)) as img:
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
            arr = np.array(img)
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def _order_points(points: np.ndarray) -> np.ndarray:
    pts = points.reshape(4, 2).astype("float32")
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).reshape(4)

    ordered = np.zeros((4, 2), dtype="float32")
    ordered[0] = pts[np.argmin(s)]      # top-left
    ordered[2] = pts[np.argmax(s)]      # bottom-right
    ordered[1] = pts[np.argmin(diff)]   # top-right
    ordered[3] = pts[np.argmax(diff)]   # bottom-left
    return ordered


def _largest_reasonable_quad(image: np.ndarray) -> Optional[np.ndarray]:
    height, width = image.shape[:2]
    image_area = float(width * height)

    scale = min(1.0, AUTO_CROP_MAX_DIMENSION / float(max(width, height)))
    if scale < 1.0:
        work = cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
    else:
        work = image.copy()

    grey = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    grey = cv2.GaussianBlur(grey, (5, 5), 0)

    # Canny plus dilation works well for books photographed on carpet/table backgrounds.
    edges = cv2.Canny(grey, 45, 130)
    kernel = np.ones((5, 5), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=1)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:12]

    for contour in contours:
        area = cv2.contourArea(contour) / (scale * scale)
        if area < image_area * 0.18:
            continue
        # If the contour is almost the whole photo, it is probably just the image boundary.
        if area > image_area * 0.94:
            continue

        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.025 * peri, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            rect = cv2.minAreaRect(contour)
            approx = cv2.boxPoints(rect).reshape(4, 1, 2)

        quad = approx.reshape(4, 2).astype("float32") / scale
        ordered = _order_points(quad)

        top_width = np.linalg.norm(ordered[1] - ordered[0])
        bottom_width = np.linalg.norm(ordered[2] - ordered[3])
        left_height = np.linalg.norm(ordered[3] - ordered[0])
        right_height = np.linalg.norm(ordered[2] - ordered[1])
        crop_width = max(top_width, bottom_width)
        crop_height = max(left_height, right_height)
        if crop_width < 200 or crop_height < 200:
            continue

        aspect = crop_width / max(crop_height, 1)
        if not 0.35 <= aspect <= 2.8:
            continue

        return ordered

    return None


def _inset_points(points: np.ndarray, fraction: float) -> np.ndarray:
    centre = points.mean(axis=0)
    return centre + (points - centre) * (1.0 - max(0.0, min(fraction, 0.12)))


def autocrop_book_cover(raw: bytes) -> Optional[bytes]:
    """Return cropped JPEG bytes, or None if confident automatic cropping is not possible."""
    image = _image_to_bgr(raw)
    if image is None:
        return None

    quad = _largest_reasonable_quad(image)
    if quad is None:
        return None

    quad = _inset_points(quad, AUTO_CROP_INSET_FRACTION)

    top_width = np.linalg.norm(quad[1] - quad[0])
    bottom_width = np.linalg.norm(quad[2] - quad[3])
    left_height = np.linalg.norm(quad[3] - quad[0])
    right_height = np.linalg.norm(quad[2] - quad[1])
    out_width = int(max(top_width, bottom_width))
    out_height = int(max(left_height, right_height))

    if out_width < 200 or out_height < 200:
        return None

    destination = np.array(
        [[0, 0], [out_width - 1, 0], [out_width - 1, out_height - 1], [0, out_height - 1]],
        dtype="float32",
    )
    transform = cv2.getPerspectiveTransform(quad.astype("float32"), destination)
    warped = cv2.warpPerspective(image, transform, (out_width, out_height))

    ok, encoded = cv2.imencode(".jpg", warped, [int(cv2.IMWRITE_JPEG_QUALITY), AUTO_CROP_JPEG_QUALITY])
    if not ok:
        return None
    return encoded.tobytes()


def _remove_existing_cover_route(app) -> None:
    app.router.routes = [
        route for route in app.router.routes
        if not (getattr(route, "path", None) == "/api/books/{book_id}/cover" and "POST" in getattr(route, "methods", set()))
    ]


def register_cover_crop_routes(app, main_module) -> None:
    """Replace the standard cover upload route with original-save plus background autocrop."""
    _remove_existing_cover_route(app)

    def _save_processed_cover(book_id: int, raw: bytes, filename: str, content_type: Optional[str], original_url: str, book_title: str) -> None:
        if not AUTO_CROP_ENABLED:
            return

        try:
            cropped = autocrop_book_cover(raw)
            if not cropped:
                with main_module.db() as conn:
                    conn.execute(
                        "INSERT INTO events(event_type, notes, created_at) VALUES (?, ?, ?)",
                        ("cover_autocrop_skipped", f"{book_title}: no confident book rectangle; kept {original_url}", main_module.now_iso()),
                    )
                return

            processed_filename = f"{Path(filename or 'cover').stem or 'cover'}-autocrop-{uuid.uuid4().hex[:8]}.jpg"
            processed_url = main_module.save_cover_bytes(book_id, cropped, processed_filename, "image/jpeg")
            with main_module.db() as conn:
                book = conn.execute("SELECT id FROM books WHERE id = ? AND deleted_at IS NULL", (book_id,)).fetchone()
                if not book:
                    return
                conn.execute("UPDATE books SET cover_url = ?, updated_at = ? WHERE id = ?", (processed_url, main_module.now_iso(), book_id))
                conn.execute(
                    "INSERT INTO events(event_type, notes, created_at) VALUES (?, ?, ?)",
                    ("cover_autocropped", f"{book_title}: {processed_url}; original={original_url}", main_module.now_iso()),
                )
        except Exception as exc:
            with main_module.db() as conn:
                conn.execute(
                    "INSERT INTO events(event_type, notes, created_at) VALUES (?, ?, ?)",
                    ("cover_autocrop_failed", f"{book_title}: {str(exc)[:180]}; kept {original_url}", main_module.now_iso()),
                )

    @app.post("/api/books/{book_id}/cover")
    def upload_book_cover_with_autocrop(
        book_id: int,
        payload: main_module.CoverUploadIn,
        background_tasks: BackgroundTasks,
        _admin: bool = Depends(main_module.require_admin),
    ):
        try:
            raw = base64.b64decode(payload.data_base64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(status_code=400, detail="Invalid base64 cover data")

        with main_module.db() as conn:
            book = conn.execute("SELECT id, title FROM books WHERE id = ? AND deleted_at IS NULL", (book_id,)).fetchone()
            if not book:
                raise HTTPException(status_code=404, detail="Book not found")
            original_url = main_module.save_cover_bytes(book_id, raw, payload.filename, payload.content_type)
            conn.execute("UPDATE books SET cover_url = ?, updated_at = ? WHERE id = ?", (original_url, main_module.now_iso(), book_id))
            conn.execute(
                "INSERT INTO events(event_type, notes, created_at) VALUES (?, ?, ?)",
                ("cover_uploaded", f"{book['title']}: {original_url}; autocrop queued", main_module.now_iso()),
            )

        background_tasks.add_task(_save_processed_cover, book_id, raw, payload.filename, payload.content_type, original_url, book["title"])
        return {
            "ok": True,
            "book_id": book_id,
            "cover_url": original_url,
            "crop_status": "queued" if AUTO_CROP_ENABLED else "disabled",
        }
