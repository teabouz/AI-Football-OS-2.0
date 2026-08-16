"""
Certificate image generation — Phase 6.

Draws a simple, clean completion certificate as a PNG using Pillow (no
external template files or system fonts required — falls back to Pillow's
built-in default font if no TrueType font is found on the host, so this
works out of the box on a bare server).
"""
import io
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1200, 800
BG_COLOR = (11, 17, 32)        # matches the dashboard's dark theme
ACCENT_COLOR = (34, 197, 94)   # green accent, matches the dashboard
TEXT_COLOR = (229, 231, 235)
MUTED_COLOR = (156, 163, 175)


def _load_font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default(size=size) if hasattr(ImageFont, "load_default") else ImageFont.load_default()


def generate_certificate_png(player_name: str, course_title: str, certificate_code: str,
                              issued_at: datetime = None) -> bytes:
    issued_at = issued_at or datetime.utcnow()
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Border
    border_margin = 30
    draw.rectangle(
        [border_margin, border_margin, WIDTH - border_margin, HEIGHT - border_margin],
        outline=ACCENT_COLOR, width=4,
    )
    draw.rectangle(
        [border_margin + 12, border_margin + 12, WIDTH - border_margin - 12, HEIGHT - border_margin - 12],
        outline=MUTED_COLOR, width=1,
    )

    font_title = _load_font(34, bold=True)
    font_heading = _load_font(54, bold=True)
    font_name = _load_font(46, bold=True)
    font_body = _load_font(26)
    font_small = _load_font(18)

    def center_text(y, text, font, fill):
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        draw.text(((WIDTH - w) / 2, y), text, font=font, fill=fill)

    center_text(90, "AI FOOTBALL OS — LEARNING ACADEMY", font_title, ACCENT_COLOR)
    center_text(180, "Certificate of Completion", font_heading, TEXT_COLOR)

    center_text(310, "This certifies that", font_body, MUTED_COLOR)
    center_text(355, player_name, font_name, ACCENT_COLOR)
    center_text(430, "has successfully completed the course", font_body, MUTED_COLOR)
    center_text(475, course_title, font_name, TEXT_COLOR)

    center_text(600, issued_at.strftime("%d %B %Y"), font_body, MUTED_COLOR)

    # Simple decorative divider
    line_y = 650
    draw.line([(WIDTH / 2 - 80, line_y), (WIDTH / 2 + 80, line_y)], fill=ACCENT_COLOR, width=2)

    center_text(HEIGHT - 90, f"Certificate ID: {certificate_code}", font_small, MUTED_COLOR)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.read()
