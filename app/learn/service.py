"""Run notebook cells 5 and 7 once for a website/route type."""

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.infra.config import settings
from app.infra.storage import (
    LearnedTemplate,
    learned_path,
    read_templates,
    read_tickets,
    temporary_root,
    template_timestamp,
    write_json_atomic,
)
from app.learn.candidates import fast_safe_extraction
from app.learn.validation import process_file_validation


def merge_templates(
    existing: list[LearnedTemplate],
    tickets: list[str],
    source_snapshot_id: str,
) -> list[LearnedTemplate]:
    templates = {}
    for template in sorted(existing, key=template_timestamp):
        templates.setdefault(template["html"], template)

    learned_at = datetime.now(timezone.utc).isoformat()
    added = 0
    for html in tickets:
        if html in templates:
            continue
        templates[html] = {
            "html": html,
            "learned_at": learned_at,
            "source_snapshot_id": source_snapshot_id,
        }
        added += 1
        if added >= settings.learn_max_new_templates:
            break

    ordered = sorted(templates.values(), key=template_timestamp)
    return ordered[-settings.learn_max_templates:]


def learn_website(
    html_path: Path,
    website_id: int,
    route_type: str,
    source_snapshot_id: str,
) -> Path:
    work_root = temporary_root()
    work_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="learn_", dir=work_root) as directory:
        candidates = fast_safe_extraction(html_path, 1, folder_name=directory)
        result = process_file_validation(candidates["output_file"], 1, output_dir=directory)
        tickets = read_tickets(Path(result["output_path"]))
        if not tickets:
            raise ValueError("Learning produced no valid ticket templates.")
        output_path = learned_path(website_id, route_type)
        existing = read_templates(output_path) if output_path.exists() else []
        merged = merge_templates(existing, tickets, source_snapshot_id)
        write_json_atomic(output_path, merged)
    return output_path
