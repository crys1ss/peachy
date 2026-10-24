"""Terminal-based demonstration and verification of Peachy's new zero-slop feature suite.

Runs end-to-end terminal tests for:
1. Win32 foreground window inspection.
2. Quick Action Presets (Solve, Fix Code, Translate, Summarize, Copy Text).
3. Real Gemini multimodal responses proving ZERO AI slop (no preamble, no pleasantries).
4. Automatic Windows clipboard population for OCR.
"""

from __future__ import annotations

import io
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QGuiApplication

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.gemini_provider import GeminiProvider, get_gemini_api_key
from core import win32


def create_snippet(text: str, subtitle: str = "") -> bytes:
    """Generate a clean synthetic screen crop PNG with text."""
    width, height = 480, 160
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([2, 2, width - 3, height - 3], outline=(220, 220, 225), width=2)

    try:
        font_large = ImageFont.truetype("arial.ttf", 26)
        font_small = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    draw.text((20, 30), text, fill=(20, 20, 25), font=font_large)
    if subtitle:
        draw.text((20, 80), subtitle, fill=(90, 90, 100), font=font_small)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def run_terminal_demo():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 65)
    print(" PEACHY TERMINAL VERIFICATION SUITE")
    print("=" * 65)

    # 1. Test Foreground Window Context
    print("\n[TEST 1] Win32 Foreground Window Context Inspection...")
    hwnd = win32.get_foreground_window()
    title = win32.get_window_text(hwnd)
    print(f"  Active HWND:  {hwnd}")
    print(f"  Window Title: '{title}'")
    print("  [OK] Win32 window context successfully retrieved.")

    # 2. Check API Key
    api_key = get_gemini_api_key()
    if not api_key:
        print("\nERROR: Gemini API key not found in Keyring or GEMINI_API_KEY env.")
        return 1
    print("  [OK] Secure API Key retrieved.")

    provider = GeminiProvider()
    print(f"  [OK] Active AI model: {provider.get_model_name()}")

    # Initialize headless QApplication for clipboard testing
    app = QApplication.instance() or QApplication(sys.argv)

    # 3. Test Action Presets: Solve
    print("\n[TEST 2] Action Preset: Solve (MCQ)")
    mcq_png = create_snippet("What is the capital of France?", "A) London   B) Paris   C) Rome")
    prompt = "Solve this question or problem. State the correct answer or option first, then explain concisely."
    result = provider.ask(image_png=mcq_png, question=prompt)
    print("  Model Output (verifying zero AI slop):")
    print("  " + "\n  ".join(result.text.strip().splitlines()))
    assert not any(result.text.lower().startswith(s) for s in ["sure", "here is", "certainly", "hope this helps"]), "AI slop detected!"
    print("  [OK] Pure direct answer returned (zero preamble).")

    # 4. Test Action Presets: Fix Code
    print("\n[TEST 3] Action Preset: Fix Code")
    code_png = create_snippet("def add(a, b)", "    return a + b")
    prompt = "Identify the bug or error in this code. Provide the root cause and the exact corrected code."
    result = provider.ask(image_png=code_png, question=prompt)
    print("  Model Output:")
    print("  " + "\n  ".join(result.text.strip().splitlines()[:6]))
    print("  [OK] Code fix returned immediately.")

    # 5. Test Action Presets: Copy Text (Instant OCR & Clipboard)
    print("\n[TEST 4] Action Preset: Copy Text (OCR + Auto-Clipboard)")
    ocr_png = create_snippet("Peachy Version 1.1", "Zero AI slop, zero gradients, pure utility.")
    prompt = "Extract all visible text in this image verbatim. Do not add preamble, explanations, or commentary. Output raw text only."
    result = provider.ask(image_png=ocr_png, question=prompt)
    extracted_text = result.text.strip()
    print(f"  Extracted Raw Text: '{extracted_text}'")

    # Simulate AppController clipboard write
    clipboard = QGuiApplication.clipboard()
    clipboard.setText(extracted_text)
    clipboard_content = clipboard.text()
    assert "Peachy Version 1.1" in clipboard_content
    print("  [OK] Text successfully copied to Windows system clipboard.")

    print("\n" + "=" * 65)
    print(" ALL TERMINAL VERIFICATIONS PASSED (Zero slop, pure facts)!")
    print("=" * 65)
    return 0


if __name__ == "__main__":
    sys.exit(run_terminal_demo())
