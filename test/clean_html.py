# html_slimmer_strict.py

from bs4 import BeautifulSoup, Tag, Comment

KEEP_ATTR_PREFIXES = ("data-", "aria-")
KEEP_ATTRS = {"id", "class", "name", "role"}

REMOVE_TAGS = {
    "svg", "symbol", "use", "img", "picture", "source",
    "canvas", "video", "audio", "iframe", "object", "embed",
    "script", "style", "link", "meta", "noscript"
}

PRESERVE_TAGS = {
    "html", "body",
    "div", "section", "article", "main", "nav", "aside",
    "header", "footer",
    "ul", "ol", "li",
    "table", "thead", "tbody", "tr", "td", "th",
    "form", "input", "button", "textarea", "select", "option", "label",
    "a",
    "p",
    "h1", "h2", "h3", "h4", "h5", "h6",
}

def _clean_attrs(tag: Tag):
    attrs = {}
    for k, v in tag.attrs.items():
        if k in KEEP_ATTRS or any(k.startswith(p) for p in KEEP_ATTR_PREFIXES):
            attrs[k] = v
    tag.attrs = attrs

def slim_html_strict(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        c.extract()

    for tag in list(soup.find_all(True)):
        if tag.name in REMOVE_TAGS:
            tag.decompose()

    for tag in list(soup.find_all(True)):
        _clean_attrs(tag)

    for tag in list(soup.find_all(True)):
        if tag.name in {"html", "body"}:
            continue

        if tag.name not in PRESERVE_TAGS:
            if tag.has_attr("id") or tag.has_attr("class"):
                continue
            if any(a.startswith("data-") or a.startswith("aria-") for a in tag.attrs.keys()):
                continue
            tag.unwrap()

    return str(soup)
