"""Shared artifact paths; only small job metadata belongs in PostgreSQL."""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from app.infra.config import settings


def storage_root() -> Path:
    root = Path(settings.storage_root)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[2] / root
    return root


def temporary_root() -> Path:
    worker_directory = os.environ.get("CRAWLER_JOB_TEMP")
    return Path(worker_directory) if worker_directory else storage_root() / "temp"


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


class LearnedTemplate(TypedDict):
    html: str
    learned_at: str
    source_snapshot_id: str | None


def template_timestamp(template: LearnedTemplate) -> datetime:
    timestamp = datetime.fromisoformat(template["learned_at"])
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def read_templates(path: Path) -> list[LearnedTemplate]:
    with path.open(encoding="utf-8") as file:
        tickets = json.load(file)
        modified_at = datetime.fromtimestamp(os.fstat(file.fileno()).st_mtime, timezone.utc).isoformat()
    if not isinstance(tickets, list) or not tickets:
        raise ValueError(f"Invalid or empty learned tickets: {path}")

    templates = []
    for item in tickets:
        if isinstance(item, str):
            item = {"html": item, "learned_at": modified_at, "source_snapshot_id": None}
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("html"), str)
            or not item["html"].strip()
            or not isinstance(item.get("learned_at"), str)
            or "source_snapshot_id" not in item
            or (item["source_snapshot_id"] is not None and (
                not isinstance(item["source_snapshot_id"], str) or not item["source_snapshot_id"].strip()
            ))
        ):
            raise ValueError(f"Invalid learned template: {path}")
        templates.append({
            "html": item["html"],
            "learned_at": template_timestamp(item).isoformat(),
            "source_snapshot_id": item["source_snapshot_id"],
        })
    return templates


def read_tickets(path: Path) -> list[str]:
    return [template["html"] for template in read_templates(path)]


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
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".atomic-", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
