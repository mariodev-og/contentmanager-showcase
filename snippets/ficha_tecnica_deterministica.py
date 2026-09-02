# Español primero · English below
# Origen: app/properties/ficha_tecnica.py del sistema en produccion (fragmento).
# Ilustra: los datos duros de la propiedad (precio, superficie, ambientes) se
# dibujan por template con Pillow, tomados de la base. El LLM no los escribe
# nunca — decision de diseno para que no alucine un precio o una zona en una
# pieza que se publica a nombre de la inmobiliaria.
#
# --- English ---
# Source: app/properties/ficha_tecnica.py from the production system (fragment).
# Shows: the property's hard data (price, area, rooms) is drawn by template with
# Pillow, taken from the database. The LLM never writes it — a design decision so
# it can't hallucinate a price or a location on a piece published under the
# agency's name.

from __future__ import annotations

import io
import os
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.brand_config import BrandConfig

FICHA_WIDTH = 1080
FICHA_HEIGHT = 1080
_BG_COLOR = "#0f172a"
_ACCENT = "#6366f1"
_WHITE = "#ffffff"
_SLATE = "#94a3b8"
_FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "fonts", "DejaVuSans.ttf")


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        if _FONT_PATH and os.path.exists(_FONT_PATH):
            return ImageFont.truetype(_FONT_PATH, size)
        return ImageFont.load_default(size)
    except (OSError, IOError):
        return ImageFont.load_default(size)


def _format_price(precio: float | None, moneda: str | None) -> str:
    if precio is None:
        return ""
    moneda = moneda or "USD"
    try:
        return f"{moneda} {precio:,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return f"{moneda} {precio}"


def render_ficha_tecnica(
    prop: dict[str, Any],
    brand: BrandConfig | None = None,
) -> bytes:
    img = Image.new("RGBA", (FICHA_WIDTH, FICHA_HEIGHT), _BG_COLOR)
    draw = ImageDraw.Draw(img)

    fotos = prop.get("fotos") or []
    if fotos and fotos[0].get("url"):
        try:
            # httpx.get sincrono: render_ficha_tecnica es sync; el get_client()
            # del proyecto es AsyncClient y devolveria una coroutine aca.
            import httpx
            resp = httpx.get(fotos[0]["url"], timeout=15.0)
            if resp.status_code == 200 and resp.content:
                bg = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                bg = bg.resize((FICHA_WIDTH, FICHA_HEIGHT), Image.LANCZOS)
                overlay = Image.new("RGBA", (FICHA_WIDTH, FICHA_HEIGHT), (15, 23, 42, 180))
                bg = Image.alpha_composite(bg, overlay)
                img = bg
                draw = ImageDraw.Draw(img)
        except Exception:
            pass

    margin = 60
    y = margin

    titulo = prop.get("titulo") or "Propiedad"
    f_title = _font(42)
    for line in _wrap_text(titulo, f_title, FICHA_WIDTH - 2 * margin):
        draw.text((margin, y), line, fill=_WHITE, font=f_title)
        y += 50
    y += 10

    precio_str = _format_price(prop.get("precio"), prop.get("moneda"))
    expensas = prop.get("expensas")
    if expensas is not None:
        precio_str += f"  +  ${expensas:,.0f} exp.".replace(",", ".")

    if precio_str:
        f_price = _font(48)
        draw.text((margin, y), precio_str, fill=_ACCENT, font=f_price)
        y += 60

    y += 20
    f_label = _font(26)
    f_val = _font(30)
    line_h = 44

    fields = [
        ("Ambientes", prop.get("ambientes")),
        ("Dormitorios", prop.get("dormitorios")),
