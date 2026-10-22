"""Unit tests for secure API key storage and lookup order."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from config import key_storage


def test_keyring_precedence_over_env(monkeypatch):
    """Verify keyring lookup takes precedence over GEMINI_API_KEY environment variable."""
    monkeypatch.setenv("GEMINI_API_KEY", "env-fake-key-12345")

    mock_keyring = MagicMock()
    mock_keyring.get_password.return_value = "keyring-fake-key-99999"

    with patch.object(key_storage, "keyring", mock_keyring):
        key = key_storage.get_api_key()
        assert key == "keyring-fake-key-99999"
        mock_keyring.get_password.assert_called_once_with("Peachy", "gemini_api_key")


def test_fallback_to_env_when_keyring_empty(monkeypatch):
    """Verify fallback to GEMINI_API_KEY when keyring has no key stored."""
    monkeypatch.setenv("GEMINI_API_KEY", "env-fake-key-12345")

    mock_keyring = MagicMock()
    mock_keyring.get_password.return_value = None

    with patch.object(key_storage, "keyring", mock_keyring):
        key = key_storage.get_api_key()
        assert key == "env-fake-key-12345"


def test_none_when_neither_keyring_nor_env_present(monkeypatch):
    """Verify get_api_key returns None when neither keyring nor env is populated."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    mock_keyring = MagicMock()
    mock_keyring.get_password.return_value = None

    with patch.object(key_storage, "keyring", mock_keyring):
        assert key_storage.get_api_key() is None


def test_set_and_delete_api_key():
    """Verify set_api_key stores to keyring and delete_api_key removes it."""
    mock_keyring = MagicMock()

    with patch.object(key_storage, "keyring", mock_keyring):
        # Set non-empty key
        ok = key_storage.set_api_key("new-fake-api-key")
        assert ok is True
        mock_keyring.set_password.assert_called_once_with("Peachy", "gemini_api_key", "new-fake-api-key")

        # Delete key
        del_ok = key_storage.delete_api_key()
        assert del_ok is True
        mock_keyring.delete_password.assert_called_once_with("Peachy", "gemini_api_key")


def test_empty_string_set_triggers_delete():
    """Verify setting an empty string or whitespace deletes the stored credential."""
    mock_keyring = MagicMock()

    with patch.object(key_storage, "keyring", mock_keyring):
        key_storage.set_api_key("   ")
        mock_keyring.delete_password.assert_called_once_with("Peachy", "gemini_api_key")
