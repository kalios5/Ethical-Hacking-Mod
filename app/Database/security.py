"""
db/security.py  -  password hashing with the LAB VULNERABILITY TOGGLE.

The mode is chosen per-user (users.hash_mode) and defaults from the
PASSWORD_HASH_MODE env var. This is the single knob that controls how hard the
"dump DB -> crack the hashes" attack is:

    secure -> werkzeug PBKDF2-SHA256, salted        (blue-team / hardened)
    weak   -> unsalted SHA-256 hex                  (crackable w/ wordlist)
    md5    -> unsalted MD5 hex                       (easiest tier)

Keep the weak/md5 modes ONLY because this is a deliberately vulnerable lab
target. Never ship unsalted hashing in real software.
"""
import hashlib

from werkzeug.security import check_password_hash, generate_password_hash

_COMMON_PASSWORDS = {
    "password", "password1", "password123", "welcome", "letmein", "qwerty",
    "admin", "supersecret", "iloveyou", "football", "monkey", "dragon",
    "abc123", "password12", "admin123", "changeme", "login", "secret",
}


def validate_password_strength(password: str, username: str | None = None, email: str | None = None) -> str | None:
    """Return a human-readable error message or None when the password meets
    the minimum strength rules for the app."""
    if not isinstance(password, str):
        return "Password must be a string."

    candidate = password.strip()
    norm = candidate.lower()
    if username:
        for variant in {username.lower(), username.lower().replace(" ", ""), username.lower().replace("_", "")}:
            if variant and norm == variant:
                return "Password must not match your username."
    if email:
        local = (email or "").split("@", 1)[0].lower()
        if local and norm == local:
            return "Password must not match your email address."

    if len(candidate) < 12:
        return "Password must be at least 12 characters long."
    if not any(ch.islower() for ch in candidate):
        return "Password must contain at least one lowercase letter."
    if not any(ch.isupper() for ch in candidate):
        return "Password must contain at least one uppercase letter."
    if not any(ch.isdigit() for ch in candidate):
        return "Password must contain at least one number."
    if not any(not ch.isalnum() for ch in candidate):
        return "Password must contain at least one special character."

    if norm in _COMMON_PASSWORDS:
        return "Password is too common; choose a more unique password."

    return None


def hash_password(plaintext: str, mode: str = "weak") -> str:
    if mode == "secure":
        return generate_password_hash(plaintext)  # pbkdf2:sha256:...
    if mode == "md5":
        return hashlib.md5(plaintext.encode()).hexdigest()
    # default / "weak"
    return hashlib.sha256(plaintext.encode()).hexdigest()


def verify_password(plaintext: str, stored_hash: str, mode: str = "weak") -> bool:
    if mode == "secure":
        return check_password_hash(stored_hash, plaintext)
    return hash_password(plaintext, mode) == stored_hash
