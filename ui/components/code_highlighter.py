"""Syntax highlighting engine for Peachy using Pygments.

Features:
- Prioritizes Cascadia Code then Consolas monospace fonts
- Formats code blocks matching Peachy Midnight and Light palettes
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

from ui.theme import ThemeTokens, get_theme


def highlight_code(code: str, language: str = "", theme: Optional[ThemeTokens] = None) -> str:
    """Format source code into styled HTML with theme syntax coloring."""
    clean_code = code.strip("\n\r")
    t = theme or get_theme()

    bg_color = t.secondary
    border_color = t.border
    text_color = t.text
    keyword_color = t.accent
    string_color = t.success
    comment_color = t.text_tertiary
    type_color = t.lavender

    if not HAS_PYGMENTS or not clean_code:
        escaped = html.escape(clean_code)
        return (
            f"<pre style=\"background-color: {bg_color}; border: 1px solid {border_color}; border-radius: 8px; "
            f"padding: 10px; font-family: 'Cascadia Code', Consolas, 'Courier New', monospace; "
            f"font-size: 12px; color: {text_color}; overflow-x: auto;\"><code>{escaped}</code></pre>"
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
            f"<pre style=\"background-color: {bg_color}; border: 1px solid {border_color}; border-radius: 8px; "
            f"padding: 10px; font-family: 'Cascadia Code', Consolas, 'Courier New', monospace; "
            f"font-size: 12px; color: {text_color}; overflow-x: auto;\"><code>{escaped}</code></pre>"
        )

    formatter = HtmlFormatter(
        nowrap=True,
        style="monokai" if t.is_dark else "friendly",
    )

    highlighted = highlight(clean_code, lexer, formatter)

    # Post-process Pygments styles to strictly match theme tokens
    color_map = {
        r'class="k"': f'style="color: {keyword_color}; font-weight: 600;"',
        r'class="kd"': f'style="color: {keyword_color}; font-weight: 600;"',
        r'class="kn"': f'style="color: {keyword_color}; font-weight: 600;"',
        r'class="s[a-z0-9]?"': f'style="color: {string_color};"',
        r'class="c[a-z0-9]?"': f'style="color: {comment_color}; font-style: italic;"',
        r'class="nc"': f'style="color: {type_color}; font-weight: 600;"',
        r'class="nf"': f'style="color: {type_color};"',
        r'class="m[a-z0-9]?"': f'style="color: {t.accent_2};"',
        r'class="o"': f'style="color: {text_color};"',
        r'class="p"': f'style="color: {t.text_secondary};"',
    }

    styled_code = highlighted
    for pattern, replacement in color_map.items():
        styled_code = re.sub(pattern, replacement, styled_code)

    return (
        f"<pre style=\"background-color: {bg_color}; border: 1px solid {border_color}; border-radius: 8px; "
        f"padding: 10px; font-family: 'Cascadia Code', Consolas, 'Courier New', monospace; "
        f"font-size: 12px; color: {text_color}; line-height: 1.45; overflow-x: auto;\">"
        f"<code>{styled_code}</code></pre>"
    )


def render_markdown_html(markdown_text: str, theme: Optional[ThemeTokens] = None) -> str:
    """Transform markdown code blocks into syntax-highlighted HTML chunks."""
    pattern = re.compile(r"```([a-zA-Z0-9_-]*)\n(.*?)```", re.DOTALL)

    def replace_code_block(match: re.Match) -> str:
        lang = match.group(1) or ""
        code = match.group(2)
        return highlight_code(code, lang, theme=theme)

    return pattern.sub(replace_code_block, markdown_text)
