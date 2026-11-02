"""Render streamed model output as Qt-friendly rich text."""

from __future__ import annotations

import re

import markdown

_HR_RE = re.compile(r"<hr\s*/?>", re.IGNORECASE)
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})", re.MULTILINE)


def _close_unterminated_fence(text: str) -> str:
    """Close a fence that is still streaming so it renders as code already."""
    fences = _FENCE_RE.findall(text)
    if len(fences) % 2:
        text += "\n" + fences[-1]
    return text


def render_markdown(text: str) -> str:
    """Convert model Markdown into HTML for ``QTextDocument``.

    The model is untrusted, so raw HTML is neutralised before parsing: only
    ``<`` needs escaping to disable tags, while leaving ``>`` intact keeps
    blockquotes and ordinary comparison text working.  Horizontal rules are
    dropped because the popover reads better without divider lines.
    """
    if not text.strip():
        return ""

    safe = _close_unterminated_fence(text.replace("<", "&lt;"))
    html = markdown.markdown(
        safe,
        extensions=["fenced_code", "tables", "sane_lists"],
        output_format="html",
    )
    return _HR_RE.sub("", html).strip()
