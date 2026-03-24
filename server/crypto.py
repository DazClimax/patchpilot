"""
Encryption helpers for sensitive settings (Telegram token, SMTP password).

Uses Fernet (AES-128-CBC + HMAC-SHA256) with a key derived from
PATCHPILOT_ADMIN_KEY via PBKDF2.  The encryption key is deterministic
for a given admin key, so settings remain readable after server restart.

Encrypted values are stored as "enc:base64..." in the DB.
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

_SALT = b"patchpilot-settings-v1"  # Static salt — key is already high-entropy


def _derive_key() -> bytes:
    """Derive a Fernet key from the admin key environment variable."""
    admin_key = os.environ.get("PATCHPILOT_ADMIN_KEY", "")
    if not admin_key:
        raise RuntimeError("PATCHPILOT_ADMIN_KEY not set — cannot encrypt/decrypt settings")
    # PBKDF2 with SHA-256, 100k iterations → 32 bytes → base64 for Fernet
    dk = hashlib.pbkdf2_hmac("sha256", admin_key.encode(), _SALT, 100_000, dklen=32)
    return base64.urlsafe_b64encode(dk)


def encrypt(plaintext: str) -> str:
    """Encrypt a string. Returns 'enc:<base64>' prefixed string."""
    if not plaintext:
        return ""
    f = Fernet(_derive_key())
    ct = f.encrypt(plaintext.encode())
    return f"enc:{ct.decode()}"


def decrypt(ciphertext: str) -> str:
    """Decrypt an 'enc:...' string. Returns plaintext.
    If not encrypted (no 'enc:' prefix), returns as-is for backward compat."""
    if not ciphertext:
        return ""
    if not ciphertext.startswith("enc:"):
        return ciphertext  # Backward compat: plaintext values still work
    try:
        f = Fernet(_derive_key())
        return f.decrypt(ciphertext[4:].encode()).decode()
    except InvalidToken:
        # Key changed or data corrupted — return empty to avoid exposing garbage
        return ""
