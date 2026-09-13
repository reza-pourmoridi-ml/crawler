"""Run notebook cells 5 and 7 once for a website/route type."""

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from bs4 import BeautifulSoup, Tag

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


def _template_fingerprint(html: str) -> tuple:
    def element_fingerprint(element: Tag) -> tuple:
        classes = tuple(sorted(set(element.get("class", ()))))
        children = tuple(
            element_fingerprint(child)
            for child in element.children
            if isinstance(child, Tag)
        )
        return element.name, classes, children

    soup = BeautifulSoup(html, "html.parser")
    return tuple(
        element_fingerprint(element)
        for element in soup.contents
        if isinstance(element, Tag)
    )


def _select_diverse_templates(tickets: list[str], existing_html: set[str], limit: int) -> list[str]:
    groups = {}
    seen = set(existing_html)
    for html in tickets:
        if html in seen:
            continue
        seen.add(html)
        groups.setdefault(_template_fingerprint(html), []).append(html)

    selected = []
    sample_index = 0
    grouped_tickets = list(groups.values())
    while len(selected) < limit:
        added = False
        for group in grouped_tickets:
            if sample_index < len(group):
                selected.append(group[sample_index])
                added = True
                if len(selected) == limit:
                    return selected
        if not added:
            break
        sample_index += 1
    return selected


def merge_templates(
    existing: list[LearnedTemplate],
    tickets: list[str],
    source_snapshot_id: str,
) -> list[LearnedTemplate]:
    templates = {}
    for template in sorted(existing, key=template_timestamp):
        templates.setdefault(template["html"], template)

    learned_at = datetime.now(timezone.utc).isoformat()
    selected = _select_diverse_templates(
        tickets,
        set(templates),
        settings.learn_max_new_templates,
    )
    for html in selected:
        templates[html] = {
            "html": html,
            "learned_at": learned_at,
            "source_snapshot_id": source_snapshot_id,
        }

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
    output_path = learned_path(website_id, route_type)
    existing = None
    incremental_tickets = []
    incremental_seen = set()

    def persist_validated_ticket(ticket: str) -> None:
        nonlocal existing
        if ticket in incremental_seen:
            return
        if existing is None:
            existing = read_templates(output_path) if output_path.exists() else []
        incremental_seen.add(ticket)
        incremental_tickets.append(ticket)
        merged = merge_templates(existing, incremental_tickets, source_snapshot_id)
        write_json_atomic(output_path, merged)

    with TemporaryDirectory(prefix="learn_", dir=work_root) as directory:
        candidates = fast_safe_extraction(html_path, 1, folder_name=directory)
        result = process_file_validation(
            candidates["output_file"],
            1,
            output_dir=directory,
            on_validated_ticket=persist_validated_ticket,
        )
        tickets = read_tickets(Path(result["output_path"]))
        if not tickets:
            raise ValueError("Learning produced no valid ticket templates.")
        if existing is None:
            existing = read_templates(output_path) if output_path.exists() else []
        merged = merge_templates(existing, tickets, source_snapshot_id)
        write_json_atomic(output_path, merged)
    return output_path
