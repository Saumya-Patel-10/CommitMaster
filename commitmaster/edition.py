"""
CommitMaster — Edition selection (User vs. Admin).
===================================================
The public Microsoft Store / GitHub build is the **user edition**: it contains no
administrator account, no admin console routing and never auto-signs-in anyone.

The private **admin edition** (admin_app.py -> CommitMaster-Admin.exe) opts in
explicitly by calling `set_admin_edition()` in code. It is intentionally NOT
switchable through environment variables or config files, so the public build
cannot be flipped into admin mode from outside.
"""

_ADMIN_EDITION = False


def set_admin_edition() -> None:
    """Mark this process as the private administrator edition."""
    global _ADMIN_EDITION
    _ADMIN_EDITION = True


def is_admin_edition() -> bool:
    return _ADMIN_EDITION
