"""One real smoke test for Gemini API multimodal image + text question.

Builds a test PNG image showing '2 + 2 = ?' using Pillow, sends it to Gemini,
and prints the resulting answer.

Usage:
    python scripts/smoke_gemini.py
"""

from __future__ import annotations

import io
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.gemini_provider import GeminiProvider, get_gemini_api_key
from ai.provider import ProviderError


def create_math_test_image() -> bytes:
    """Create a test PNG image with text '2 + 2 = ?' using Pillow."""
    width, height = 320, 160
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Draw border
    draw.rectangle([4, 4, width - 5, height - 5], outline=(200, 200, 200), width=2)

    text = "2 + 2 = ?"
    # Try to load a default font or standard font
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except Exception:
        font = ImageFont.load_default()

    # Center text
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (width - text_w) // 2
    y = (height - text_h) // 2
    draw.text((x, y), text, fill=(20, 20, 20), font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def main() -> int:
    print("=" * 60)
    print("Peachy: Gemini Provider Smoke Test")
    print("=" * 60)

    api_key = get_gemini_api_key()
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable is not set.")
        return 1

    print("Generating test image ('2 + 2 = ?')...")
    image_bytes = create_math_test_image()
    print(f"Test image generated ({len(image_bytes)} bytes PNG).")

    provider = GeminiProvider()
    print(f"Sending multimodal request using model '{provider.get_model_name()}'...")

    try:
        result = provider.ask(
            image_png=image_bytes,
            question="What is the answer to the equation in this image?",
        )
        print("\n--- Gemini Response ---")
        print(result.text)
        print("-----------------------")
        print(f"\nHistory turns: {len(result.history)}")
        print("SMOKE TEST SUCCESSFUL!")
        return 0

    except ProviderError as err:
        print(f"\nProvider Error: {type(err).__name__}: {err.message}")
        return 1
    except Exception as err:
        print(f"\nUnexpected Error: {type(err).__name__}: {err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
