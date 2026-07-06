from __future__ import annotations

import json
import os
from typing import Optional

from .cache import app_data_dir

try:
    import keyring
except Exception:  # pragma: no cover - volitelná závislost
    keyring = None


class TokenStore:
    def __init__(self, service_name: str = "KajovoPhotoSelector"):
        self.service_name = service_name
        self._fallback_path = os.path.join(app_data_dir(service_name), "cloud_tokens.json")
        self._warning_message = ""

    @property
    def warning_message(self) -> str:
        return self._warning_message

    def _read_fallback(self) -> dict:
        if not os.path.exists(self._fallback_path):
            return {}
        try:
            with open(self._fallback_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return {}

    def _write_fallback(self, data: dict) -> None:
        os.makedirs(os.path.dirname(self._fallback_path), exist_ok=True)
        old_umask = os.umask(0)
        try:
            fd = os.open(self._fallback_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        finally:
            os.umask(old_umask)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        self._warning_message = (
            "Systémový keyring není dostupný. Tokeny jsou uložené v lokálním souboru s právy 0600."
        )

    def get_token(self, account_key: str) -> Optional[str]:
        if keyring is not None:
            try:
                value = keyring.get_password(self.service_name, account_key)
                if value is not None:
                    return value
            except Exception:
                pass
        return self._read_fallback().get(account_key)

    def set_token(self, account_key: str, token_value: str) -> None:
        if keyring is not None:
            try:
                keyring.set_password(self.service_name, account_key, token_value)
                return
            except Exception:
                pass
        data = self._read_fallback()
        data[account_key] = token_value
        self._write_fallback(data)

    def delete_token(self, account_key: str) -> None:
        if keyring is not None:
            try:
                keyring.delete_password(self.service_name, account_key)
                return
            except Exception:
                pass
        data = self._read_fallback()
        if account_key in data:
            del data[account_key]
            self._write_fallback(data)
