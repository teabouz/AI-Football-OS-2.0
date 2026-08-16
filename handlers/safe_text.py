"""Helpers for safely embedding user/AI text in Telegram legacy Markdown."""
from telegram.helpers import escape_markdown


def md(text) -> str:
    """Escape text that will be interpolated into parse_mode='Markdown'."""
    return escape_markdown(str(text or ""), version=1)
