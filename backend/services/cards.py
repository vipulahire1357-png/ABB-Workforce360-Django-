from __future__ import annotations

from io import BytesIO
from importlib.resources import files
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.graphics.barcode import code128

from backend.config import settings

W, H = 54 * mm, 86 * mm
RED = HexColor("#e60000")
NAVY = HexColor("#182433")
MUTED = HexColor("#586575")
LOGO_W, LOGO_H = 22 * mm, 9 * mm


class CardAssetError(Exception):
    """A required stored worker image or official logo is missing or invalid."""


def _font_names() -> tuple[str, str]:
    regular, bold = "Helvetica", "Helvetica-Bold"
    font_dir = settings.font_dir or Path(str(files("reportlab").joinpath("fonts")))
    names = (("WIRCardRegular", font_dir / "Vera.ttf"), ("WIRCardBold", font_dir / "VeraBd.ttf"))
    try:
        for name, path in names:
            if path.is_file() and name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, str(path)))
        if all(path.is_file() for _, path in names):
            return "WIRCardRegular", "WIRCardBold"
    except Exception:
        pass
    return regular, bold


def _split_word(word: str, font: str, size: float, max_width: float) -> list[str]:
    chunks: list[str] = []
    current = ""
    for char in word:
        candidate = current + char
        if current and pdfmetrics.stringWidth(candidate, font, size) > max_width:
            chunks.append(current)
            current = char
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _wrap(text: str, font: str, size: float, max_width: float) -> list[str]:
    words = str(text).split()
    lines: list[str] = []
    line = ""
    for word in words:
        pieces = _split_word(word, font, size, max_width)
        for piece in pieces:
            candidate = f"{line} {piece}".strip()
            if line and pdfmetrics.stringWidth(candidate, font, size) > max_width:
                lines.append(line)
                line = piece
            else:
                line = candidate
    if line:
        lines.append(line)
    return lines or [""]


def _fit_lines(text: str, font: str, start: float, minimum: float, max_width: float, max_lines: int) -> tuple[list[str], float]:
    size = start
    while size >= minimum:
        lines = _wrap(text, font, size, max_width)
        if len(lines) <= max_lines:
            return lines, size
        size = round(size - 0.2, 2)
    return _wrap(text, font, minimum, max_width), minimum


def _draw_lines(c: canvas.Canvas, lines: list[str], x: float, y: float, font: str, size: float, leading: float) -> None:
    c.setFont(font, size)
    for line in lines:
        c.drawString(x, y, line)
        y -= leading


def _draw_lines_centered(c: canvas.Canvas, lines: list[str], center_x: float, y: float, font: str, size: float, leading: float) -> None:
    c.setFont(font, size)
    for line in lines:
        c.drawCentredString(center_x, y, line)
        y -= leading


def _draw_logo(c: canvas.Canvas, x: float, y: float, box_w: float, box_h: float) -> None:
    logo = settings.logo_path
    if not logo.is_file():
        raise CardAssetError("The official ABB logo asset is missing.")

    try:
        if logo.suffix.lower() == ".svg":
            from reportlab.graphics import renderPDF
            from svglib.svglib import svg2rlg

            drawing = svg2rlg(str(logo))
            if drawing is None or not drawing.width or not drawing.height:
                raise ValueError("SVG has no drawable dimensions")
            scale = min(box_w / drawing.width, box_h / drawing.height)
            c.saveState()
            c.translate(x + (box_w - drawing.width * scale) / 2, y + (box_h - drawing.height * scale) / 2)
            c.scale(scale, scale)
            renderPDF.draw(drawing, c, 0, 0)
            c.restoreState()
        else:
            c.drawImage(ImageReader(str(logo)), x, y, width=box_w, height=box_h, preserveAspectRatio=True, mask="auto", anchor="c")
    except Exception as exc:
        raise CardAssetError("The official ABB logo asset is invalid.") from exc


def _draw_header(c: canvas.Canvas, title: str, regular: str, bold: str) -> None:
    _draw_logo(c, 4 * mm, H - 11 * mm, 15 * mm, 6 * mm)
    c.setFillColor(NAVY)
    c.setFont(bold, 6.8)
    c.drawString(4 * mm, H - 16 * mm, title)


def _draw_card_base(c: canvas.Canvas) -> None:
    c.setFillColor(white)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setStrokeColor(HexColor("#b8c2cb"))
    c.setLineWidth(0.45)
    c.roundRect(1 * mm, 1 * mm, W - 2 * mm, H - 2 * mm, 2.8 * mm, fill=0, stroke=1)


def _draw_barcode(c: canvas.Canvas, worker, y: float, max_width: float, regular: str, bold: str) -> None:
    module_w = 0.16 * mm
    barcode = code128.Code128(worker.worker_id, barHeight=7.5 * mm, barWidth=module_w, humanReadable=False, quiet=True)
    if barcode.width > max_width:
        fixed_quiet = barcode.lquiet + barcode.rquiet
        encoded_width = barcode.width - fixed_quiet
        if fixed_quiet >= max_width or encoded_width <= 0:
            raise ValueError("Worker ID barcode does not fit the card safe area")
        module_w *= (max_width - fixed_quiet) / encoded_width
        barcode = code128.Code128(worker.worker_id, barHeight=7.5 * mm, barWidth=module_w, humanReadable=False, quiet=True)
    if barcode.width > max_width + 0.01 * mm:
        raise ValueError("Worker ID barcode does not fit the card safe area")
    barcode.drawOn(c, (W - barcode.width) / 2, y)
    c.setFillColor(NAVY)
    c.setFont(regular, 5.2)
    c.drawCentredString(W / 2, y - 2.2 * mm, worker.worker_id)


def _format_contact(value: str) -> str:
    """Format local Indian 10-digit numbers like the supplied card reference."""
    digits = str(value)
    if len(digits) == 10:
        return f"+91 {digits[:5]} {digits[5:]}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+91 {digits[2:7]} {digits[7:]}"
    return digits


def _photo_reader(worker) -> ImageReader:
    photo_path = settings.upload_dir / Path(worker.photo_path).name
    try:
        with Image.open(photo_path) as source:
            if source.format not in ("JPEG", "JPG"):
                raise CardAssetError("The registered worker photo is not a valid JPEG.")
            oriented = ImageOps.exif_transpose(source).convert("RGB")
            target_size = (round(24 * mm / 25.4 * 300), round(29 * mm / 25.4 * 300))
            portrait = ImageOps.fit(oriented, target_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.43))
            buffer = BytesIO()
            portrait.save(buffer, format="JPEG", quality=94, subsampling=0, optimize=False)
            buffer.seek(0)
            return ImageReader(buffer)
    except CardAssetError:
        raise
    except (FileNotFoundError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise CardAssetError("The registered worker photo is missing or invalid.") from exc


def _draw_front(c: canvas.Canvas, worker, regular: str, bold: str) -> None:
    _draw_card_base(c)
    _draw_header(c, "ABB PLANT-3 WORKER ID", regular, bold)

    photo_x, photo_y, photo_w, photo_h = 15 * mm, 35.5 * mm, 24 * mm, 27 * mm
    c.drawImage(_photo_reader(worker), photo_x, photo_y, width=photo_w, height=photo_h, preserveAspectRatio=False, mask="auto")
    c.setStrokeColor(HexColor("#000000")); c.setLineWidth(0.55)
    c.rect(photo_x, photo_y, photo_w, photo_h, fill=0, stroke=1)

    identity_x, identity_w = 4 * mm, W - 8 * mm
    c.setFillColor(NAVY)
    name_y, name_leading = photo_y - 3.8 * mm, 3.0 * mm
    name_lines, name_size = _fit_lines(str(worker.name).upper(), bold, 8.2, 5.8, identity_w, 2)
    _draw_lines_centered(c, name_lines, W / 2, name_y, bold, name_size, name_leading)

    contractor_y = name_y - (len(name_lines) - 1) * name_leading - 2.5 * mm
    contractor_lines, contractor_size = _fit_lines(worker.contractor_name, bold, 6.8, 5.2, identity_w, 1)
    _draw_lines_centered(c, contractor_lines, W / 2, contractor_y, bold, contractor_size, 2.8 * mm)
    barcode_y = 8.5 * mm
    _draw_barcode(c, worker, barcode_y, W - 8 * mm, regular, bold)


def _draw_back(c: canvas.Canvas, worker, regular: str, bold: str) -> None:
    _draw_card_base(c)
    _draw_header(c, "ABB PLANT-3 WORKER DETAILS", regular, bold)

    rows = (
        ("WORKER NO.", worker.worker_no),
        ("JOINING DATE", worker.joining_date.strftime("%d/%m/%Y")),
        ("CONTACT NO.", _format_contact(worker.contact_no)),
        ("EMERGENCY CONTACT", _format_contact(worker.emergency_contact)),
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
        if pdfmetrics.stringWidth(str(value), regular, fitted_size) > available:
            value_text = _wrap(str(value), regular, fitted_size, available)[0]
            if len(_wrap(str(value), regular, fitted_size, available)) > 1:
                raise ValueError(f"{label} value cannot fit on the card without overlap")
        else:
            value_text = str(value)
        c.setFillColor(NAVY)
        c.setFont(regular, fitted_size)
        c.drawString(label_x, baseline - 3.5 * mm, value_text)
        c.setStrokeColor(HexColor("#d9dfe5"))
        c.setLineWidth(0.35)
        separator_y = baseline - 6 * mm
        c.line(label_x, separator_y, value_right, separator_y)

    _draw_barcode(c, worker, 7.3 * mm, W - 8 * mm, regular, bold)


def card_pdf(worker) -> bytes:
    """Build a deterministic, duplex-ready vertical CR80 PDF from a stored worker record."""
    out = BytesIO()
    regular, bold = _font_names()
    c = canvas.Canvas(out, pagesize=(W, H), pageCompression=1, invariant=1)
    _draw_front(c, worker, regular, bold)
    c.showPage()
    _draw_back(c, worker, regular, bold)
    c.showPage()
    c.save()
    return out.getvalue()
