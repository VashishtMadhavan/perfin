"""Secret storage for access tokens.

Plaid access tokens never go into SQLite. We first try the platform keyring; if
that is unavailable, we fall back to a chmod-600 JSON file in the app data dir.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol

import keyring
from keyring.errors import KeyringError

from perfin.config import SECRETS_FALLBACK_PATH

SERVICE_NAME = "perfin"


class SecretStore(Protocol):
    def get(self, ref: str) -> str | None: ...
    def set(self, ref: str, value: str) -> None: ...
    def delete(self, ref: str) -> None: ...


class KeyringStore:
    def get(self, ref: str) -> str | None:
        return keyring.get_password(SERVICE_NAME, ref)

    def set(self, ref: str, value: str) -> None:
        keyring.set_password(SERVICE_NAME, ref, value)

    def delete(self, ref: str) -> None:
        try:
            keyring.delete_password(SERVICE_NAME, ref)
        except KeyringError:
            pass


class FileFallbackStore:
    def __init__(self, path: Path = SECRETS_FALLBACK_PATH) -> None:
        self._path = path

    def get(self, ref: str) -> str | None:
        return self._load().get(ref)

    def set(self, ref: str, value: str) -> None:
        data = self._load()
        data[ref] = value
        self._save(data)

    def delete(self, ref: str) -> None:
        data = self._load()
        data.pop(ref, None)
        self._save(data)

    def _load(self) -> dict[str, str]:
        if not self._path.is_file():
            return {}
        with self._path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return {str(k): str(v) for k, v in raw.items()}

    def _save(self, data: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
        os.chmod(tmp, 0o600)
        tmp.replace(self._path)
        os.chmod(self._path, 0o600)


class DefaultSecretStore:
    """Keyring first, JSON fallback when keyring is unavailable."""

    def __init__(self, fallback: SecretStore | None = None) -> None:
        self._keyring = KeyringStore()
        self._fallback = fallback or FileFallbackStore()

    def get(self, ref: str) -> str | None:
        try:
            value = self._keyring.get(ref)
        except KeyringError:
            return self._fallback.get(ref)
        return value if value is not None else self._fallback.get(ref)

    def set(self, ref: str, value: str) -> None:
        try:
            self._keyring.set(ref, value)
        except KeyringError:
            self._fallback.set(ref, value)

    def delete(self, ref: str) -> None:
        try:
            self._keyring.delete(ref)
        except KeyringError:
            self._fallback.delete(ref)


def plaid_access_token_ref(item_id: str) -> str:
    return f"plaid/{item_id}/access-token"
