"""List available Gemini models supporting content generation.

Usage:
    python scripts/list_models.py

Security Note:
    Reads GEMINI_API_KEY from environment. The key value is never printed or logged.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google import genai
from google.genai import errors

from ai.gemini_provider import get_gemini_api_key


def main() -> int:
    api_key = get_gemini_api_key()
    if not api_key:
        print("ERROR: GEMINI_API_KEY is not set in the environment.")
        print("Please set the GEMINI_API_KEY environment variable before running this script.")
        return 1

    print("=" * 70)
    print("Peachy: Available Gemini Content Generation Models")
    print("=" * 70)

    try:
        client = genai.Client(api_key=api_key)
        pager = client.models.list()

        count = 0
        flash_models = []
        other_models = []

        for model in pager:
            actions = getattr(model, "supported_actions", None) or []
            if "generateContent" in actions or "generate_content" in actions:
                count += 1
                name = model.name or ""
                # Strip 'models/' prefix if present for clean settings display
                short_name = name.removeprefix("models/")
                display_name = getattr(model, "display_name", short_name)
                input_limit = getattr(model, "input_token_limit", "N/A")
                desc = (getattr(model, "description", "") or "").strip()

                info = {
                    "name": short_name,
                    "display": display_name,
                    "input_limit": input_limit,
                    "desc": desc,
                }
                if "flash" in short_name.lower():
                    flash_models.append(info)
                else:
                    other_models.append(info)

        print(f"\nFound {count} model(s) supporting content generation.\n")

        print("--- Recommended Flash Models (Vision Capable & Fast) ---")
        for m in flash_models:
            print(f"  • Model: {m['name']:<25} [{m['display']}]")
            if m["desc"]:
                # Print first sentence of description
                summary = m["desc"].split(".")[0] + "."
                print(f"    Description: {summary}")
            print(f"    Input Token Limit: {m['input_limit']}")
            print()

        print("--- Other Available Models ---")
        for m in other_models:
            print(f"  • Model: {m['name']:<25} [{m['display']}]")

        print("=" * 70)
        print("To select a model, set it in settings.json or env var PEACHY_MODEL.")
        print("=" * 70)
        return 0

    except errors.APIError as err:
        print(f"API Error ({err.code}): {err.message}")
        return 1
    except Exception as err:
        print(f"Unexpected error: {err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
