"""CommitMaster Demo / Staging entry point.

Own process, own data directory, own local database. It will not start
against a production server and it will not activate the admin product.
"""
from __future__ import annotations

import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from commitmaster import product

product.activate("demo")

os.environ["COMMITMASTER_PRODUCT"] = "demo"
os.environ.setdefault("APP_ENVIRONMENT", "staging")


def _refuse_production_server() -> None:
    from commitmaster import database as db

    url = (db.get_server_url() or "").strip()
    if not url:
        return
    try:
        import requests
        response = requests.get(f"{url.rstrip('/')}/api/health", timeout=6, headers={
            "X-CommitMaster-Product": "demo",
        })
        environment = ""
        if response.headers.get("content-type", "").startswith("application/json"):
            environment = (response.json() or {}).get("environment", "")
    except Exception as exc:
        raise SystemExit(f"Demo app could not verify the staging server: {exc}")
    if environment != "staging":
        raise SystemExit(
            "Demo app refuses this server. /api/health did not report environment=staging."
        )


def main() -> None:
    if product.current() != "demo":
        raise SystemExit("demo entry point lost its product lock")
    _refuse_production_server()
    import app
    app.launch_app()


if __name__ == "__main__":
    main()
