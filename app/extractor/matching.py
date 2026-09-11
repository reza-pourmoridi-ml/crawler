"""Ported from test-ollama.ipynb; keep the tested algorithms unchanged."""

from bs4 import BeautifulSoup, Tag

threshold = 0.95

def normalize_tag(tag: Tag):
    classes = tuple(tag.get("class", []))

    children = tuple(
        normalize_tag(child)
        for child in tag.children
        if isinstance(child, Tag)
    )
    return tag.name, classes, children


def get_root_tag(html: str) -> Tag:
    soup = BeautifulSoup(html, "html.parser")
    root_tags = [
        tag for tag in soup.contents
        if isinstance(tag, Tag)
    ]
    if len(root_tags) != 1:
        raise ValueError("هر item باید دقیقاً یک تگ ریشه داشته باشد.")
    return root_tags[0]


def tag_similarity(a: Tag, b: Tag) -> float:
    score = 0.0
    total = 0.0

    # tag name
    total += 1
    score += 1.0 if a.name == b.name else 0.0

    # classes
    total += 1
    a_classes = set(a.get("class", []))
    b_classes = set(b.get("class", []))
    if a_classes or b_classes:
        score += len(a_classes & b_classes) / len(a_classes | b_classes)
    else:
        score += 1.0

    # children
    total += 1
    a_children = [c for c in a.children if isinstance(c, Tag)]
    b_children = [c for c in b.children if isinstance(c, Tag)]

    if not a_children and not b_children:
        score += 1.0
    elif a_children and b_children:
        n = min(len(a_children), len(b_children))
        child_score = sum(
            tag_similarity(a_children[i], b_children[i]) for i in range(n)
        ) / max(len(a_children), len(b_children))
        score += child_score
    else:
        score += 0.0

    return score / total


def find_all_matching_items(page_html: str, items: list[str]):
    page_soup = BeautifulSoup(page_html, "html.parser")
    page_tags = page_soup.find_all(True)

    item_roots = [
        get_root_tag(item)
        for item in items
    ]
    unique_matches = []
    
    for page_tag in page_tags:
        if any(
            tag_similarity(page_tag, item_root) >= threshold
            for item_root in item_roots
        ):
            unique_matches.append(page_tag)
    
    return list(dict.fromkeys(unique_matches))
