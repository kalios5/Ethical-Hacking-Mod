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
