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

def set_admin_edition() -> None:
    """Mark this process as the private administrator edition.

    This cannot escalate a process that the user or demo entry point already locked.
    """
    from commitmaster import product
    product.activate("admin")


def is_admin_edition() -> bool:
    from commitmaster import product
    return product.is_admin()
