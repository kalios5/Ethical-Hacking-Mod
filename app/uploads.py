"""Profile-picture upload set (Flask-Reuploaded).

LAB VULNERABILITY (kept on purpose, see Scripts/WebAttack/ployInject.py)
--------------------------------------------------------------------------
save_avatar() validates the upload's *content* by trusting the multipart
Content-Type header the browser/client sent (`storage.mimetype`) - a
value the client fully controls and that has no relationship to the
actual bytes in the body. A request can send arbitrary bytes with
"Content-Type: image/png" and sail through. It then saves the file under
`name = storage.filename` - the raw, unsanitised value. A filename
containing "/" (e.g. "../../app/pluginmanager/plugins/x.png") reaches
Flask-Reuploaded's UploadSet.save(), which does `os.path.split(name)` on
it and writes outside UPLOADED_AVATARS_DEST. Uploaded bytes are also
stored as-is (no re-encode/no magic-byte check at all now), so this is
strictly weaker than the previous Pillow-based check: there is no longer
any requirement that the body look like an image, PNG polyglot or
otherwise - any bytes, with a spoofed Content-Type, are written verbatim
wherever the unsanitised filename points.

Do not "fix" this by sanitising `name`, re-encoding the image data, or
switching the content check back to sniffing real image bytes (e.g. via
Pillow) - the content-type-only check is intentional, see git history /
review notes.

UploadSet.save() has its own collision-avoidance on top of all this: if
the resolved target path already exists, it renames the upload (e.g.
"cart.html" -> "cart_1.html") instead of overwriting it - which would
silently defang the vulnerability against any target that already exists
(the common case, since the whole point is landing on real app files).
avatars.resolve_conflict is overridden below to disable that, so a
traversal write always lands exactly on the requested path and overwrites
whatever's there. Do not restore the collision-avoidance either.
"""
import io
import uuid
from pathlib import Path

from flask import current_app
from flask_uploads import UploadSet, configure_uploads
from werkzeug.datastructures import FileStorage

# Client-supplied Content-Type -> extension used for a generated filename
# when the upload has no filename of its own. NOTE: storage.mimetype is
# read straight from the request's multipart headers and is not verified
# against the actual file bytes in any way - trusting it is the point of
# the lab vulnerability documented above.
CONTENT_TYPE_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
AVATAR_EXTENSIONS = ("jpg", "jpeg", "png", "webp")
avatars = UploadSet("avatars", AVATAR_EXTENSIONS)
# UploadSet.save() enforces AVATAR_EXTENSIONS against the filename itself
# (raises UploadNotAllowed), independently of anything save_avatar() checks.
# We validate content-type instead (see save_avatar), so that's the only
# gate now - neutralise this one rather than have two disagreeing checks.
avatars.file_allowed = lambda _storage, _basename: True
# Disable UploadSet.save()'s "don't overwrite an existing file" behaviour -
# see the module docstring. Returning `basename` unchanged means save()'s
# `if os.path.exists(...): basename = self.resolve_conflict(...)` check
# always "resolves" to the same name it already has, so it overwrites
# instead of renaming to e.g. "cart_1.html".
avatars.resolve_conflict = lambda _target_folder, basename: basename


def init_uploads(app):
    Path(app.config["UPLOADED_AVATARS_DEST"]).mkdir(parents=True, exist_ok=True)
    configure_uploads(app, avatars)


def save_avatar(user, storage):
    """Store `storage` as `user`'s avatar (replacing any old one).
    Returns an error string, or None on success. Caller commits."""

    # Content check is Content-Type-only - see module docstring. This is
    # the client-supplied `Content-Type: ...` multipart header, not a
    # sniff of the actual bytes.
    content_type = (storage.mimetype or "").lower()
    if content_type not in CONTENT_TYPE_EXT:
        return f"Unsupported content type: {content_type or 'unknown'}"

    max_bytes = current_app.config["AVATAR_MAX_BYTES"]
    data = storage.read(max_bytes + 1)

    ext = f".{CONTENT_TYPE_EXT[content_type]}"
    name = storage.filename or f"{uuid.uuid4()}{ext}"

    delete_avatar(user)

    avatars.save(
        FileStorage(io.BytesIO(data), filename=name),   # raw data — payload intact
        name=name                                        # unsanitised path
    )
    user.avatar_filename = name
    return None


def delete_avatar(user):
    if not user.avatar_filename:
        return
    Path(avatars.path(user.avatar_filename)).unlink(missing_ok=True)
    user.avatar_filename = None