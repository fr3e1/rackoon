"""Password hashing and signed session cookies (stdlib only)."""

import base64
import hashlib
import hmac
import secrets
import time

COOKIE_NAME = "sm_session"
SESSION_TTL = 7 * 24 * 3600


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    return hmac.compare_digest(digest.hex(), digest_hex)


def make_token(secret: str, password_hash: str) -> str:
    # Binding the token to the password hash means changing the password
    # invalidates every existing session.
    expires = str(int(time.time()) + SESSION_TTL)
    sig = _sign(secret, password_hash, expires)
    return base64.urlsafe_b64encode(f"{expires}.{sig}".encode()).decode()


def check_token(token: str | None, secret: str, password_hash: str | None) -> bool:
    if not token or not password_hash:
        return False
    try:
        expires, sig = base64.urlsafe_b64decode(token.encode()).decode().split(".")
    except Exception:
        return False
    if int(expires) < time.time():
        return False
    return hmac.compare_digest(sig, _sign(secret, password_hash, expires))


def _sign(secret: str, password_hash: str, expires: str) -> str:
    return hmac.new(secret.encode(), f"{password_hash}|{expires}".encode(), hashlib.sha256).hexdigest()
