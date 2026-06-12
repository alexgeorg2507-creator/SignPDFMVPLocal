"""Рендер страниц PDF с подсветкой найденных мест подписи. v1.17.7

Размер подписи в preview соответствует тому что будет в итоговом PDF
(overlay.py: DEFAULT_SIGNATURE_HEIGHT_PT=42pt, масштабируется по scale).
v1.14.0: use_marker / marker_color — превью маркера места подписи.
v1.17.7: позиция подписи (X) берётся из той же core-функции
         _find_underscore_anchor, что и финальный PDF — превью больше не
         клеит подпись на левый край bbox (на слово "Заказчик").
"""
import io

import fitz
from PIL import Image, ImageDraw

# Позиция подписи — единый источник истины с финальным overlay.
# Если core по какой-то причине недоступен — fallback на левый край bbox.
try:
    from signfinder.pdf.overlay import _find_underscore_anchor as _core_anchor
except Exception:  # pragma: no cover
    _core_anchor = None

# Константы в sync с overlay.py
_DEFAULT_SIG_HEIGHT_PT = 42
_MAX_SIG_HEIGHT_PT = 85
_MIN_SIG_HEIGHT_PT = 20


def render_page_with_highlights(
    pdf_bytes: bytes,
    page_num: int,
    matches_on_page: list,
    scale: float = 1.5,
    signature_png: bytes = None,
    sig_scale: float = 1.0,
    use_marker: bool = False,
    marker_color: str = "pink",
) -> bytes:
    """Рендерит страницу PDF в PNG с превью подписи и/или маркера.

    Активный якорь: PNG подписи вставляется в размере идентичном overlay.py.
    Выключенный якорь: серая рамка.
    use_marker: рисует прямоугольный маркер на правом поле (sync с overlay.py).
    marker_color: "pink" | "gray".
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[page_num]
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    sig_orig = None
    sig_resized = None
    if signature_png:
        try:
            sig_orig = Image.open(io.BytesIO(signature_png)).convert("RGBA")
            sig_h_pt = min(
                max(_MIN_SIG_HEIGHT_PT, _DEFAULT_SIG_HEIGHT_PT * sig_scale),
                _MAX_SIG_HEIGHT_PT,
            )
            sig_h_px = max(1, int(sig_h_pt * scale))
            aspect = sig_orig.width / sig_orig.height if sig_orig.height else 1.0
            sig_w_px = max(1, int(sig_h_px * aspect))
            sig_resized = sig_orig.resize((sig_w_px, sig_h_px), Image.LANCZOS)
        except Exception:
            sig_orig = None
            sig_resized = None

    img = img.convert("RGBA")
    draw = ImageDraw.Draw(img)

    for m in matches_on_page:
        x0, y0, x1, y1 = m.bbox
        box_w = max(1, int((x1 - x0) * scale))
        box_h = max(1, int((y1 - y0) * scale))
        bx = int(x0 * scale)
        by = int(y0 * scale)

        if m.operator_excluded or sig_resized is None:
            draw.rectangle((bx, by, bx + box_w, by + box_h), outline="gray", width=2)
        else:
            # Позиция подписи — та же, что в финальном PDF (overlay).
            # Подпись клеится на подчёркивание правее текста-якоря ("Заказчик"),
            # а не на левый край bbox.
            paste_x = bx
            paste_y = by + box_h - sig_resized.height
            if _core_anchor is not None:
                try:
                    anchor_x, anchor_y_bottom, _ = _core_anchor(
                        page, m.bbox, getattr(m, "pattern", "") or "",
                    )
                    paste_x = int(anchor_x * scale)
                    paste_y = int(anchor_y_bottom * scale) - sig_resized.height
                except Exception:
                    pass
            img.paste(sig_resized, (paste_x, paste_y), sig_resized)

        # Маркер места подписи (sync с overlay.py: 11.3×34pt от правого края)
        if use_marker and not m.operator_excluded:
            MARKER_W = max(1, int(11.3 * scale))
            MARKER_H = max(1, int(34.0 * scale))
            MARGIN   = max(1, int(3.0 * scale))
            y_center_px = int(((m.bbox[1] + m.bbox[3]) / 2) * scale)
            mx0 = img.width - MARGIN - MARKER_W
            my0 = y_center_px - MARKER_H // 2
            mx1 = img.width - MARGIN
            my1 = y_center_px + MARKER_H // 2
            fill = (255, 182, 193, 220) if marker_color != "gray" else (180, 180, 180, 220)
            draw.rectangle((mx0, my0, mx1, my1), fill=fill)

    doc.close()
    img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
