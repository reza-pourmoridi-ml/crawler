"""Run notebook cells 5 and 7 once for a website/route type."""

from pathlib import Path
from tempfile import TemporaryDirectory

from app.infra.storage import learned_path, read_tickets, storage_root, write_json_atomic
from app.learn.candidates import fast_safe_extraction
from app.learn.validation import process_file_validation


def learn_website(html_path: Path, website_id: int, route_type: str) -> Path:
    temporary_root = storage_root() / "temp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="learn_", dir=temporary_root) as directory:
        candidates = fast_safe_extraction(html_path, 1, folder_name=directory)
        result = process_file_validation(candidates["output_file"], 1, output_dir=directory)
        # Empty/failed validation must never replace a working template or reset its age.
        tickets = read_tickets(Path(result["output_path"]))
        output_path = learned_path(website_id, route_type)
        write_json_atomic(output_path, tickets)
    return output_path
