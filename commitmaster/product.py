"""Process product identity.

Three products share this repository and must not share runtime privilege:

* user — public Microsoft Store app
* admin — private administrator console
* demo — staging app with no production data

The entry point locks the product once. A locked user or demo process cannot
escalate to admin. Environment variables and config files cannot escalate it.
"""
from __future__ import annotations

_PRODUCT: str | None = None

_UNPRIVILEGED = ("user", "demo")
_ALL = ("user", "admin", "demo")

DATA_DIR_NAMES = {
    "user": "CommitMaster",
    "admin": "CommitMaster-Admin",
    "demo": "CommitMaster-Demo",
}


class ProductError(RuntimeError):
    """Raised when code tries to change a process's product privilege."""


def activate(name: str) -> None:
    """Lock this process to a product. Escalation is refused."""
    global _PRODUCT
    if name not in _ALL:
        raise ProductError(f"unknown product {name!r}")
    if _PRODUCT is None:
        _PRODUCT = name
        return
    if _PRODUCT == name:
        return
    raise ProductError(f"product is locked to {_PRODUCT}; refusing to become {name}")


def current() -> str:
    """Return the locked product, or user when nothing has locked yet."""
    return _PRODUCT or "user"


def is_locked() -> bool:
    return _PRODUCT is not None


def is_admin() -> bool:
    return current() == "admin"


def is_demo() -> bool:
    return current() == "demo"


def is_user() -> bool:
    return current() == "user"


def data_dir_name() -> str:
    return DATA_DIR_NAMES[current()]
