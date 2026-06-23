"""Almacén seguro de credenciales (Windows Credential Manager)."""

from __future__ import annotations

try:
    import keyring
    from keyring.errors import KeyringError
except ImportError:  # pragma: no cover
    keyring = None  # type: ignore[assignment]

    class KeyringError(Exception):
        pass


SERVICE_NAME = "HeimdallTimeWatch"
ACCOUNT_CLOUD_KEY = "ollama_cloud_key"
_fallback_key = ""


def _keyring_available() -> bool:
    return keyring is not None


def get_cloud_api_key() -> str:
    global _fallback_key
    if _keyring_available():
        try:
            stored = keyring.get_password(SERVICE_NAME, ACCOUNT_CLOUD_KEY)
            if stored:
                return stored
        except KeyringError:
            pass
    return _fallback_key


def set_cloud_api_key(value: str) -> None:
    global _fallback_key
    cleaned = (value or "").strip()
    if _keyring_available():
        try:
            if cleaned:
                keyring.set_password(SERVICE_NAME, ACCOUNT_CLOUD_KEY, cleaned)
            else:
                try:
                    keyring.delete_password(SERVICE_NAME, ACCOUNT_CLOUD_KEY)
                except KeyringError:
                    pass
            _fallback_key = ""
            return
        except KeyringError as exc:
            raise RuntimeError(
                "No se pudo guardar la API key en el Credential Manager de Windows."
            ) from exc
    _fallback_key = cleaned
