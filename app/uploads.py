"""Profile-picture upload set (Flask-Reuploaded). Deliberately excludes svg/gif:
svg can carry script, and every upload is re-encoded by Pillow anyway."""
import io
import os
import uuid

from flask import current_app
from flask_uploads import UploadSet, configure_uploads
from werkzeug.datastructures import FileStorage

AVATAR_EXTENSIONS = ("jpg", "jpeg", "png", "webp")
avatars = UploadSet("avatars", AVATAR_EXTENSIONS)


def init_uploads(app):
    os.makedirs(app.config["UPLOADED_AVATARS_DEST"], exist_ok=True)
    configure_uploads(app, avatars)


def _reencode(data, size):
    """Validate `data` as a real jpeg/png/webp and return square PNG bytes,
    or raise ValueError. Re-encoding drops EXIF and any appended payload."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        probe = Image.open(io.BytesIO(data))
        probe.verify()
        img = Image.open(io.BytesIO(data))
        if img.format not in ("JPEG", "PNG", "WEBP"):
            raise ValueError("Profile picture must be a JPG, PNG or WEBP image.")
        if img.width > 4096 or img.height > 4096:
            raise ValueError("Image dimensions are too large (max 4096px).")
        img = ImageOps.exif_transpose(img).convert("RGBA")
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValueError("That file is not a valid image.")
    img = ImageOps.fit(img, (size, size))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def save_avatar(user, storage):
    """Store `storage` as `user`'s avatar (replacing any old one).
    Returns an error string, or None on success. Caller commits."""
    max_bytes = current_app.config["AVATAR_MAX_BYTES"]
    data = storage.read(max_bytes + 1)
    if len(data) > max_bytes:
        return f"Profile picture must be under {max_bytes // (1024 * 1024)} MB."
    if not avatars.file_allowed(storage, storage.filename):
        return "Profile picture must be a JPG, PNG or WEBP image."
    try:
        png = _reencode(data, current_app.config["AVATAR_SIZE"])
    except ValueError as exc:
        return str(exc)
    name = f"{uuid.uuid4().hex}.png"
    avatars.save(FileStorage(io.BytesIO(png), filename=name), name=name)
    delete_avatar(user)
    user.avatar_filename = name
    return None


def delete_avatar(user):
    if not user.avatar_filename:
        return
    try:
        os.remove(avatars.path(user.avatar_filename))
    except OSError:
        pass
    user.avatar_filename = None
