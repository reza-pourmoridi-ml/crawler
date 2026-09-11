"""Shared artifact paths; only small job metadata belongs in PostgreSQL."""

import json
import os
import tempfile
from pathlib import Path

from app.infra.config import settings


def storage_root() -> Path:
    root = Path(settings.storage_root)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[2] / root
    return root


def website_directory(website_id: int, route_type: str) -> Path:
    if route_type not in {"domestic", "international"}:
        raise ValueError(f"Unsupported route type: {route_type}")
    return Path(f"website_{int(website_id)}") / route_type


def learned_path(website_id: int, route_type: str) -> Path:
    return storage_root() / "learned" / website_directory(website_id, route_type) / "tickets.json"


def snapshot_directory(payload: dict) -> Path:
    # A separate directory per crawl prevents a later crawl overwriting learn input.
    snapshot_id = str(payload["snapshot_id"])
    if len(snapshot_id) != 32 or any(c not in "0123456789abcdef" for c in snapshot_id):
        raise ValueError("Invalid snapshot_id")
    return (storage_root() / "raw" / website_directory(payload["website_id"], payload["route_type"])
            / f"request_{int(payload['search_request_id'])}" / snapshot_id)


def extracted_path(payload: dict) -> Path:
    return (storage_root() / "extracted" / website_directory(payload["website_id"], payload["route_type"])
            / f"scrape_{int(payload['source_job_id'])}.json")


def read_tickets(path: Path) -> list[str]:
    tickets = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(tickets, list) or not tickets or any(
        not isinstance(item, str) or not item.strip() for item in tickets
    ):
        raise ValueError(f"Invalid or empty learned tickets: {path}")
    return tickets


def usable_learning(website_id: int, route_type: str) -> bool:
    try:
        read_tickets(learned_path(website_id, route_type))
        return True
    except (OSError, ValueError):
        return False


def write_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
