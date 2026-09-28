"""Internet tools — free, no keys: DuckDuckGo search + page reader."""
import re
import urllib.request
from html.parser import HTMLParser


def web_search(query: str, n: int = 3) -> str:
    """Short DuckDuckGo results: title — snippet — url."""
    try:
        from ddgs import DDGS
    except ImportError:
        return "Web search unavailable (pip install ddgs)."
    try:
        out = []
        with DDGS() as ddg:
            for r in ddg.text(query, max_results=n):
                out.append(f"{r.get('title', '')} — "
                           f"{r.get('body', '')[:160]} [{r.get('href', '')}]")
        return " | ".join(out) if out else "No results."
    except Exception as e:
        return f"Search failed: {str(e)[:100]}"


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self._skip = [], False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "header", "footer"):
            self._skip = True

    def handle_endtag(self, tag):
        self._skip = False

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def read_page(url: str, limit: int = 1500) -> str:
    """Fetch a page, return visible text (trimmed)."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (F1-Engineer)"})
        with urllib.request.urlopen(req, timeout=12) as r:
            html = r.read().decode("utf-8", "ignore")
        p = _Text()
        p.feed(html)
        text = re.sub(r"\s+", " ", " ".join(p.parts))
        return text[:limit] if text else "Page had no readable text."
    except Exception as e:
        return f"Could not read page: {str(e)[:100]}"
