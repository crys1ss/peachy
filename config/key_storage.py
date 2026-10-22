"""Secure API key storage using Windows Credential Manager via keyring.

Lookup order:
1. keyring (Windows Credential Manager), service name "Peachy", username "gemini_api_key"
2. GEMINI_API_KEY environment variable

The API key is NEVER written to settings.json, logs, or crash dumps.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

try:
    import keyring
except ImportError:
    keyring = None  # type: ignore

logger = logging.getLogger(__name__)

SERVICE_NAME = "Peachy"
KEY_USERNAME = "gemini_api_key"


def get_api_key() -> Optional[str]:
    """Retrieve API key following strict lookup order: keyring, then environment."""
    # 1. Check Keyring (Windows Credential Manager)
    if keyring is not None:
        try:
            stored_key = keyring.get_password(SERVICE_NAME, KEY_USERNAME)
            if stored_key and stored_key.strip():
                return stored_key.strip()
        except Exception as exc:
            logger.warning("Error reading API key from keyring: %s", exc)

    # 2. Check Environment Variable GEMINI_API_KEY
    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()

    return None


def set_api_key(api_key: str) -> bool:
    """Store the API key securely into Windows Credential Manager."""
    if keyring is None:
        logger.error("Keyring module is unavailable. Cannot store key.")
        return False

    cleaned_key = api_key.strip()
    if not cleaned_key:
        return delete_api_key()

    try:
        keyring.set_password(SERVICE_NAME, KEY_USERNAME, cleaned_key)
        logger.info("API key successfully stored in Windows Credential Manager.")
        return True
    except Exception as exc:
        logger.error("Failed to store API key in keyring: %s", exc)
        return False


def delete_api_key() -> bool:
    """Remove API key from Windows Credential Manager."""
    if keyring is None:
        return False

    try:
        keyring.delete_password(SERVICE_NAME, KEY_USERNAME)
        logger.info("API key deleted from Windows Credential Manager.")
        return True
    except Exception as exc:
        logger.debug("Keyring delete_password returned: %s", exc)
        return False


def has_keyring_key() -> bool:
    """Check if an API key is stored in the OS credential manager."""
    if keyring is None:
        return False
    try:
        k = keyring.get_password(SERVICE_NAME, KEY_USERNAME)
        return bool(k and k.strip())
    except Exception:
        return False


def get_key_source() -> str:
    """Return 'keyring', 'environment', or 'none' indicating key origin."""
    if has_keyring_key():
        return "keyring"
    if os.environ.get("GEMINI_API_KEY"):
        return "environment"
    return "none"
