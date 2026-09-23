"""
app/pluginmanager/sandbox.py  -  application-level filesystem containment
for third-party plugin execution.

WHAT THIS IS
------------
A context manager that, while active, replaces the built-in open() with a
wrapper that refuses to open any path outside an allowed directory (the
plugin's own folder). The intent is to stop an uploaded plugin's
render_widget() from reading or writing arbitrary files on the host -
e.g. /etc/passwd, other tenants' data, or app config/secrets.

Robust filesystem isolation of untrusted code cannot be enforced from
inside the same Python process as that code. It requires an OS/container
boundary - unprivileged user, mount namespaces, seccomp - which is what
this project's Part 2 (Docker) layer is for. This guard demonstrates the
concept and raises the bar against a naive file-stealing payload; it is
explicitly a partial, in-process control, not true containment.
"""
import builtins
import contextlib
import os

_real_open = builtins.open


def _is_within(path, allowed_dir):
    try:
        resolved = os.path.realpath(path)
    except (OSError, ValueError):
        return False
    allowed_real = os.path.realpath(allowed_dir)
    return resolved == allowed_real or resolved.startswith(allowed_real + os.sep)


@contextlib.contextmanager
def restricted_filesystem(allowed_dir):
    """While active, builtin open() may only touch paths inside allowed_dir.
    Reads and writes outside it raise PermissionError. Restores the real
    open() on exit, even if the plugin raised."""

    def guarded_open(file, mode="r", *args, **kwargs):
        # `file` can be a path-like or an already-open fd (int). An int fd
        # is already-obtained access, nothing to gate here.
        if isinstance(file, int):
            return _real_open(file, mode, *args, **kwargs)
        if not _is_within(os.fspath(file), allowed_dir):
            raise PermissionError(
                f"Plugin attempted to access a path outside its own folder: {file!r}"
            )
        return _real_open(file, mode, *args, **kwargs)

    builtins.open = guarded_open
    try:
        yield
    finally:
        builtins.open = _real_open
