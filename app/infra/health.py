"""Small dependency-free health probes for container healthchecks."""

from __future__ import annotations

import argparse
import os
import urllib.request

from sqlalchemy import text

from app.infra.config import settings
from app.infra.db import SessionLocal


def database() -> None:
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))


def http() -> None:
    port = os.getenv("CONTROL_PORT", str(settings.control_port))
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/control/status", timeout=3) as response:
        if response.status >= 400:
            raise RuntimeError(f"HTTP health returned {response.status}")


def control() -> None:
    http()
    database()


def ollama() -> None:
    with urllib.request.urlopen(f"{settings.ollama_host.rstrip('/')}/api/tags", timeout=3) as response:
        if response.status >= 400:
            raise RuntimeError(f"Ollama health returned {response.status}")


def learn() -> None:
    database()
    ollama()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("probe", choices=("database", "http", "control", "ollama", "learn"))
    args = parser.parse_args()
    globals()[args.probe]()
