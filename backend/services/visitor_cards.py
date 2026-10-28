"""Visitor ID-card PDF generation — reuses worker card layout from cards.py."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.graphics.barcode import code128

from backend.config import settings
from backend.services.cards import (
    W, H, RED, NAVY, MUTED,
    _font_names, _fit_lines, _draw_lines_centered,
    _draw_logo, _draw_header, _draw_card_base, _format_contact,
    CardAssetError,
)


def _visitor_photo_reader(visitor) -> ImageReader | None:
    """Load a visitor photo, or return None if no photo was uploaded."""
    if not visitor.photo_path:
        return None
    photo_path = settings.visitor_upload_dir / Path(visitor.photo_path).name
    try:
        with Image.open(photo_path) as source:
            if source.format not in ("JPEG", "JPG"):
                raise CardAssetError("The visitor photo is not a valid JPEG.")
            oriented = ImageOps.exif_transpose(source).convert("RGB")
            target_size = (round(24 * mm / 25.4 * 300), round(29 * mm / 25.4 * 300))
            portrait = ImageOps.fit(oriented, target_size,
                                    method=Image.Resampling.LANCZOS, centering=(0.5, 0.43))
            buffer = BytesIO()
            portrait.save(buffer, format="JPEG", quality=94, subsampling=0, optimize=False)
            buffer.seek(0)
            return ImageReader(buffer)
    except CardAssetError:
        raise
    except (FileNotFoundError, UnidentifiedImageError, OSError, ValueError):
        return None  # Missing visitor photo is not fatal; card omits the photo


def _draw_barcode_for_id(c: canvas.Canvas, id_value: str, y: float,
                         max_width: float, regular: str) -> None:
    """Draw a Code128 barcode for the given ID string."""
    module_w = 0.16 * mm
    barcode = code128.Code128(id_value, barHeight=7.5 * mm, barWidth=module_w,
                              humanReadable=False, quiet=True)
    if barcode.width > max_width:
        fixed_quiet = barcode.lquiet + barcode.rquiet
        encoded_width = barcode.width - fixed_quiet
        if fixed_quiet >= max_width or encoded_width <= 0:
            raise ValueError("Visitor ID barcode does not fit the card safe area")
        module_w *= (max_width - fixed_quiet) / encoded_width
        barcode = code128.Code128(id_value, barHeight=7.5 * mm, barWidth=module_w,
                                  humanReadable=False, quiet=True)
    barcode.drawOn(c, (W - barcode.width) / 2, y)
    c.setFillColor(NAVY)
    c.setFont(regular, 5.2)
    c.drawCentredString(W / 2, y - 2.2 * mm, id_value)


def _draw_visitor_front(c: canvas.Canvas, visitor, regular: str, bold: str) -> None:
    _draw_card_base(c)
    _draw_header(c, "ABB PLANT-3 VISITOR ID", regular, bold)

    # Photo (optional)
    photo_x, photo_y, photo_w, photo_h = 15 * mm, 35.5 * mm, 24 * mm, 27 * mm
    reader = _visitor_photo_reader(visitor)
    if reader:
        c.drawImage(reader, photo_x, photo_y, width=photo_w, height=photo_h,
                    preserveAspectRatio=False, mask="auto")
        c.setStrokeColor(HexColor("#000000"))
        c.setLineWidth(0.55)
        c.rect(photo_x, photo_y, photo_w, photo_h, fill=0, stroke=1)
    else:
        # Placeholder outline
        c.setStrokeColor(HexColor("#b8c2cb"))
        c.setLineWidth(0.4)
        c.rect(photo_x, photo_y, photo_w, photo_h, fill=0, stroke=1)
        c.setFillColor(MUTED)
        c.setFont(regular, 6)
        c.drawCentredString(photo_x + photo_w / 2, photo_y + photo_h / 2 - 2, "VISITOR")

    # Name
    identity_x, identity_w = 4 * mm, W - 8 * mm
    c.setFillColor(NAVY)
    name_y, name_leading = photo_y - 3.8 * mm, 3.0 * mm
    name_lines, name_size = _fit_lines(str(visitor.name).upper(), bold, 8.2, 5.8, identity_w, 2)
    _draw_lines_centered(c, name_lines, W / 2, name_y, bold, name_size, name_leading)

    # Company + Location
    detail_y = name_y - (len(name_lines) - 1) * name_leading - 2.5 * mm
    detail_text = visitor.company_name
    if visitor.location:
        detail_text = f"{visitor.company_name} · {visitor.location}"
    detail_lines, detail_size = _fit_lines(detail_text, bold, 6.8, 4.8, identity_w, 2)
    _draw_lines_centered(c, detail_lines, W / 2, detail_y, bold, detail_size, 2.8 * mm)

    # Barcode
    _draw_barcode_for_id(c, visitor.visitor_id, 8.5 * mm, W - 8 * mm, regular)


def _draw_visitor_back(c: canvas.Canvas, visitor, regular: str, bold: str) -> None:
    _draw_card_base(c)
    _draw_header(c, "ABB PLANT-3 VISITOR DETAILS", regular, bold)

    rows = (
        ("VISITOR NO.", visitor.visitor_no),
        ("HOST", visitor.host),
        ("CONTACT NO.", _format_contact(visitor.contact_no)),
        ("PURPOSE", visitor.purpose),
    )
    label_x, value_right = 5 * mm, W - 5 * mm
    baselines = (62.5 * mm, 50.5 * mm, 38.5 * mm, 26.5 * mm)
    label_size, value_size = 5.8, 6.6

    for (label, value), baseline in zip(rows, baselines):
        c.setFillColor(MUTED)
        c.setFont(bold, label_size)
        c.drawString(label_x, baseline, label)
        available = value_right - label_x
        fitted_size = value_size
        while fitted_size > 5.2 and pdfmetrics.stringWidth(str(value), regular, fitted_size) > available:
            fitted_size = round(fitted_size - 0.2, 2)
        value_text = str(value)
        if pdfmetrics.stringWidth(value_text, regular, fitted_size) > available:
            from backend.services.cards import _wrap
            wrapped = _wrap(value_text, regular, fitted_size, available)
            value_text = wrapped[0]
        c.setFillColor(NAVY)
        c.setFont(regular, fitted_size)
        c.drawString(label_x, baseline - 3.5 * mm, value_text)
        c.setStrokeColor(HexColor("#d9dfe5"))
        c.setLineWidth(0.35)
        c.line(label_x, baseline - 6 * mm, value_right, baseline - 6 * mm)

    # Barcode on back side
    _draw_barcode_for_id(c, visitor.visitor_id, 7.3 * mm, W - 8 * mm, regular)


def visitor_card_pdf(visitor) -> bytes:
    """Build a two-page CR80 visitor ID-card PDF matching the worker card format."""
    out = BytesIO()
    regular, bold = _font_names()
    c = canvas.Canvas(out, pagesize=(W, H), pageCompression=1, invariant=1)
    _draw_visitor_front(c, visitor, regular, bold)
    c.showPage()
    _draw_visitor_back(c, visitor, regular, bold)
    c.showPage()
    c.save()
    return out.getvalue()
