from pathlib import Path

from app.extractor.matching import find_all_matching_items
from app.extractor.tickets import extract_ticket_item
from app.infra.storage import read_tickets


def extract_tickets(html_path: Path, template_path: Path, airlines: dict) -> list[dict]:
    matches = find_all_matching_items(
        page_html=html_path.read_text(encoding="utf-8"),
        items=read_tickets(template_path),
    )
    return [extract_ticket_item(str(item), airlines) for item in matches]
