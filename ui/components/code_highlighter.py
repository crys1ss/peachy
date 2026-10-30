"""Syntax highlighting engine for Peachy using Pygments.

Features:
- Prioritizes Cascadia Code then Consolas monospace fonts
- Formats code blocks matching Midnight Peachy palette:
  - Background: #111118
  - Border: #292735
  - Keywords: #FF6BCE
  - Strings: #79E2B5
  - Types/Names: #B9A4FF
  - Numbers: #F5A4DE
  - Comments: #A6A1B3
- Robust fallback if Pygments is unavailable or lexer fails
"""

from __future__ import annotations

import html
import re
from typing import Optional

try:
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name, guess_lexer
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False


def highlight_code(code: str, language: str = "") -> str:
    """Format source code into styled HTML with Midnight Peachy syntax coloring."""
    clean_code = code.strip("\n\r")

    if not HAS_PYGMENTS or not clean_code:
        escaped = html.escape(clean_code)
        return (
            f"<pre style=\"background-color: #111118; border: 1px solid #292735; border-radius: 8px; "
            f"padding: 10px; font-family: 'Cascadia Code', Consolas, 'Courier New', monospace; "
            f"font-size: 12px; color: #F6F3FA; overflow-x: auto;\"><code>{escaped}</code></pre>"
        )

    lexer = None
    lang = language.strip().lower()
    if lang:
        try:
            lexer = get_lexer_by_name(lang, stripall=True)
        except Exception:
            lexer = None

    if lexer is None:
        try:
            lexer = guess_lexer(clean_code)
        except Exception:
            try:
                lexer = get_lexer_by_name("text")
            except Exception:
                lexer = None

    if lexer is None:
        escaped = html.escape(clean_code)
        return (
            f"<pre style=\"background-color: #111118; border: 1px solid #292735; border-radius: 8px; "
            f"padding: 10px; font-family: 'Cascadia Code', Consolas, 'Courier New', monospace; "
            f"font-size: 12px; color: #F6F3FA; overflow-x: auto;\"><code>{escaped}</code></pre>"
        )

    formatter = HtmlFormatter(
        nowrap=True,
        style="monokai",
    )

    highlighted = highlight(clean_code, lexer, formatter)

    # Post-process Pygments styles to strictly match Midnight tokens:
    # Replace default colors with Midnight palette
    color_map = {
        r'class="k"': 'style="color: #FF6BCE; font-weight: 600;"',   # Keyword -> Pink
        r'class="kd"': 'style="color: #FF6BCE; font-weight: 600;"',  # Keyword.Declaration
        r'class="kn"': 'style="color: #FF6BCE; font-weight: 600;"',  # Keyword.Namespace
        r'class="s[a-z0-9]?"': 'style="color: #79E2B5;"',            # Strings -> Success Green
        r'class="c[a-z0-9]?"': 'style="color: #A6A1B3; font-style: italic;"', # Comments -> Text Secondary
        r'class="nc"': 'style="color: #B9A4FF; font-weight: 600;"',  # Name.Class -> Lavender
        r'class="nf"': 'style="color: #B9A4FF;"',                     # Name.Function -> Lavender
        r'class="m[a-z0-9]?"': 'style="color: #F5A4DE;"',            # Numbers -> Pink Soft
        r'class="o"': 'style="color: #F6F3FA;"',                     # Operators -> Text
        r'class="p"': 'style="color: #A6A1B3;"',                     # Punctuation -> Text Secondary
    }

    styled_code = highlighted
    for pattern, replacement in color_map.items():
        styled_code = re.sub(pattern, replacement, styled_code)

    return (
        f"<pre style=\"background-color: #111118; border: 1px solid #292735; border-radius: 8px; "
        f"padding: 10px; font-family: 'Cascadia Code', Consolas, 'Courier New', monospace; "
        f"font-size: 12px; color: #F6F3FA; line-height: 1.45; overflow-x: auto;\">"
        f"<code>{styled_code}</code></pre>"
    )


def render_markdown_html(markdown_text: str) -> str:
    """Transform markdown code blocks into syntax-highlighted HTML chunks."""
    # Find ```lang\ncode\n``` blocks
    pattern = re.compile(r"```([a-zA-Z0-9_-]*)\n(.*?)```", re.DOTALL)

    def replace_code_block(match: re.Match) -> str:
        lang = match.group(1) or ""
        code = match.group(2)
        return highlight_code(code, lang)

    return pattern.sub(replace_code_block, markdown_text)

