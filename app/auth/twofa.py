"""
app/auth/twofa.py  -  TOTP-based two-factor authentication helpers.
"""
import base64
import io

import pyotp
import qrcode

ISSUER = "Petal & Stem"


def generate_secret():
    return pyotp.random_base32()


def provisioning_uri(user):
    return pyotp.TOTP(user.twofa_secret).provisioning_uri(
        name=user.email or user.username, issuer_name=ISSUER
    )


def qr_data_uri(user):
    img = qrcode.make(provisioning_uri(user))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def verify_code(user, code):
    if not user.twofa_secret or not code:
        return False
    return pyotp.TOTP(user.twofa_secret).verify(code.strip(), valid_window=1)
