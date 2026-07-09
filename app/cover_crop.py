import base64
import binascii
import os
import uuid
from io import BytesIO
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Depends, HTTPException
from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat


AUTO_CROP_ENABLED = os.getenv("AUTO_CROP_COVER_PHOTOS", "true").strip().lower() not in {"0", "false", "no", "off"}
AUTO_CROP_INSET_FRACTION = float(os.getenv("AUTO_CROP_INSET_FRACTION", "0.025"))
AUTO_CROP_MAX_DIMENSION = int(os.getenv("AUTO_CROP_MAX_DIMENSION", "1600"))
AUTO_CROP_JPEG_QUALITY = int(os.getenv("AUTO_CROP_JPEG_QUALITY", "88"))
AUTO_CROP_EDGE_PADDING = int(os.getenv("AUTO_CROP_EDGE_PADDING", "8"))


def _open_rgb_image(raw: bytes) -> Optional[Image.Image]:
    """Decode image bytes using Pillow and respect iPhone EXIF orientation."""
    try:
        with Image.open(BytesIO(raw)) as img:
            img = ImageOps.exif_transpose(img)
            return img.convert("RGB")
    except Exception:
        return None


def _resize_for_processing(image: Image.Image) -> tuple[Image.Image, float]:
    width, height = image.size
    max_dim = max(width, height)
    if max_dim <= AUTO_CROP_MAX_DIMENSION:
        return image.copy(), 1.0

    scale = AUTO_CROP_MAX_DIMENSION / float(max_dim)
    resized = image.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
    return resized, scale


def _corner_background_colour(image: Image.Image) -> tuple[int, int, int]:
    """Estimate the background colour from the four corners of the uploaded photo."""
    width, height = image.size
    patch = max(20, min(width, height) // 12)
    boxes = [
        (0, 0, patch, patch),
        (width - patch, 0, width, patch),
        (0, height - patch, patch, height),
        (width - patch, height - patch, width, height),
    ]

    values = []
    for box in boxes:
        stat = ImageStat.Stat(image.crop(box))
        values.append(tuple(int(v) for v in stat.median))

    return tuple(sorted(channel)[len(channel) // 2] for channel in zip(*values))


def _mask_non_background(image: Image.Image) -> Image.Image:
    """Create a mask of areas that are visually different from the estimated background."""
    background = Image.new("RGB", image.size, _corner_background_colour(image))
    diff = ImageChops.difference(image, background).convert("L")

    # Smooth carpet / table texture while keeping the book edge as a larger contiguous region.
    diff = diff.filter(ImageFilter.GaussianBlur(radius=2))

    # Auto threshold from image statistics with a sensible floor for low-contrast books.
    stat = ImageStat.Stat(diff)
    threshold = max(24, min(70, int(stat.mean[0] + stat.stddev[0] * 0.65)))
    mask = diff.point(lambda px: 255 if px > threshold else 0)

    # Close small holes and remove speckle noise from carpet texture.
    mask = mask.filter(ImageFilter.MaxFilter(9))
    mask = mask.filter(ImageFilter.MinFilter(9))
    mask = mask.filter(ImageFilter.MaxFilter(5))
    return mask


def _find_content_bbox(mask: Image.Image, image_size: tuple[int, int]) -> Optional[tuple[int, int, int, int]]:
    bbox = mask.getbbox()
    if not bbox:
        return None

    width, height = image_size
    left, top, right, bottom = bbox
    crop_w = right - left
    crop_h = bottom - top
    image_area = width * height
    crop_area = crop_w * crop_h

    if crop_w < width * 0.25 or crop_h < height * 0.25:
        return None
    if crop_area > image_area * 0.96:
        return None

    aspect = crop_w / max(crop_h, 1)
    if not 0.35 <= aspect <= 2.8:
        return None

    return bbox


def _inset_bbox(bbox: tuple[int, int, int, int], image_size: tuple[int, int], fraction: float) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    inset_x = max(AUTO_CROP_EDGE_PADDING, int(width * max(0.0, min(fraction, 0.12))))
    inset_y = max(AUTO_CROP_EDGE_PADDING, int(height * max(0.0, min(fraction, 0.12))))

    img_w, img_h = image_size
    return (
        max(0, left + inset_x),
        max(0, top + inset_y),
        min(img_w, right - inset_x),
        min(img_h, bottom - inset_y),
    )


def autocrop_book_cover(raw: bytes) -> Optional[bytes]:
    """Return cropped JPEG bytes, or None if confident automatic cropping is not possible.

    This intentionally uses Pillow only. It avoids OpenCV/NumPy because many small NAS and
    Raspberry Pi-style targets do not have suitable OpenCV wheels and should not be compiling
    image-processing stacks during Docker builds.
    """
    image = _open_rgb_image(raw)
    if image is None:
        return None

    work, scale = _resize_for_processing(image)
    mask = _mask_non_background(work)
    bbox = _find_content_bbox(mask, work.size)
    if bbox is None:
        return None

    if scale != 1.0:
        bbox = tuple(int(v / scale) for v in bbox)

    bbox = _inset_bbox(bbox, image.size, AUTO_CROP_INSET_FRACTION)
    left, top, right, bottom = bbox
    if right <= left or bottom <= top:
        return None

    cropped = image.crop(bbox)
    output = BytesIO()
    cropped.save(output, format="JPEG", quality=AUTO_CROP_JPEG_QUALITY, optimise=True)
    return output.getvalue()


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
                        ("cover_autocrop_skipped", f"{book_title}: no confident book boundary; kept {original_url}", main_module.now_iso()),
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
