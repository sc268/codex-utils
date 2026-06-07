#!/usr/bin/env python3
"""Local MCP stdio server providing web_search and web_fetch.

This exists so Claude can search and fetch the web even when ANTHROPIC_BASE_URL
points at a gateway that lacks Anthropic's server-side WebSearch/WebFetch tools.
Everything here runs locally over the network, so it works regardless of base URL.

No API keys required:
  - web_search uses DuckDuckGo's free HTML endpoint.
  - web_fetch does a plain HTTP GET and converts HTML to readable text.

Protocol: newline-delimited JSON-RPC 2.0 over stdin/stdout (MCP stdio transport).
Pure standard library, no third-party dependencies.
"""

import html
import json
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "claude-yolo-web"
SERVER_VERSION = "1.0.0"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 20
MAX_FETCH_BYTES = 5_000_000
DEFAULT_FETCH_CHARS = 20_000


# --------------------------------------------------------------------------- #
# Web search (DuckDuckGo HTML endpoint, no API key)
# --------------------------------------------------------------------------- #

_RESULT_LINK_RE = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_SNIPPET_RE = re.compile(
    r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(fragment: str) -> str:
    text = _TAG_RE.sub("", fragment)
    return html.unescape(text).strip()


def _decode_ddg_href(href: str) -> str:
    """DuckDuckGo wraps result links in a redirect carrying uddg=<encoded-url>."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urllib.parse.urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        params = urllib.parse.parse_qs(parsed.query)
        target = params.get("uddg", [None])[0]
        if target:
            return urllib.parse.unquote(target)
    return href


def web_search(query: str, max_results: int = 8) -> str:
    query = (query or "").strip()
    if not query:
        return "Error: empty search query."

    max_results = max(1, min(int(max_results or 8), 20))
    data = urllib.parse.urlencode({"q": query, "kl": "us-en"}).encode("utf-8")
    request = urllib.request.Request(
        "https://html.duckduckgo.com/html/",
        data=data,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - surface any failure to the caller
        return f"Error: web search request failed: {exc}"

    links = _RESULT_LINK_RE.findall(body)
    snippets = _SNIPPET_RE.findall(body)

    if not links:
        return f"No results found for: {query}"

    lines = [f"Search results for: {query}", ""]
    for index, (href, title_html) in enumerate(links[:max_results]):
        url = _decode_ddg_href(href)
        title = _strip_tags(title_html) or url
        snippet = _strip_tags(snippets[index]) if index < len(snippets) else ""
        lines.append(f"{index + 1}. {title}")
        lines.append(f"   {url}")
        if snippet:
            lines.append(f"   {snippet}")
        lines.append("")

    return "\n".join(lines).rstrip()


# --------------------------------------------------------------------------- #
# Web fetch (HTTP GET + HTML -> text)
# --------------------------------------------------------------------------- #


class _TextExtractor(HTMLParser):
    """Collect visible text, dropping script/style and noisy containers."""

    _SKIP = {"script", "style", "noscript", "template", "svg", "head"}
    _BLOCK = {
        "p", "br", "div", "section", "article", "header", "footer",
        "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in self._BLOCK:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self._chunks.append(data)

    def get_text(self) -> str:
        text = "".join(self._chunks)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n[ \t]+", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def web_fetch(url: str, max_chars: int = DEFAULT_FETCH_CHARS) -> str:
    url = (url or "").strip()
    if not url:
        return "Error: empty url."
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url

    max_chars = max(500, min(int(max_chars or DEFAULT_FETCH_CHARS), 100_000))
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
    )

    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as resp:
            final_url = resp.geturl()
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(MAX_FETCH_BYTES)
    except Exception as exc:  # noqa: BLE001 - surface any failure to the caller
        return f"Error: fetch failed for {url}: {exc}"

    charset = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type, re.IGNORECASE)
    if match:
        charset = match.group(1)
    body = raw.decode(charset, errors="replace")

    if "html" in content_type.lower() or (not content_type and "<html" in body.lower()):
        extractor = _TextExtractor()
        try:
            extractor.feed(body)
            text = extractor.get_text()
        except Exception:  # noqa: BLE001 - fall back to raw on parser failure
            text = _strip_tags(body)
    else:
        text = body.strip()

    truncated = ""
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = f"\n\n[truncated to {max_chars} chars]"

    header = f"Fetched: {final_url}\nContent-Type: {content_type or 'unknown'}\n\n"
    return header + text + truncated


# --------------------------------------------------------------------------- #
# MCP tool registry
# --------------------------------------------------------------------------- #

TOOLS = [
    {
        "name": "web_search",
        "description": (
            "Search the web via DuckDuckGo and return ranked results with titles, "
            "URLs, and snippets. Use this to find current information online."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
                "max_results": {
                    "type": "integer",
                    "description": "Number of results to return (1-20, default 8).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_fetch",
        "description": (
            "Fetch a URL over HTTP and return its readable text content "
            "(HTML is converted to plain text). Use after web_search to read a page."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to fetch."},
                "max_chars": {
                    "type": "integer",
                    "description": "Max characters to return (default 20000).",
                },
            },
            "required": ["url"],
        },
    },
]


def _call_tool(name: str, arguments: dict) -> str:
    arguments = arguments or {}
    if name == "web_search":
        return web_search(
            arguments.get("query", ""),
            arguments.get("max_results", 8),
        )
    if name == "web_fetch":
        return web_fetch(
            arguments.get("url", ""),
            arguments.get("max_chars", DEFAULT_FETCH_CHARS),
        )
    raise ValueError(f"unknown tool: {name}")


# --------------------------------------------------------------------------- #
# JSON-RPC / MCP stdio loop
# --------------------------------------------------------------------------- #


def _send(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _result(request_id, result) -> None:
    _send({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id, code, message) -> None:
    _send({
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    })


def _handle(message: dict) -> None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    # Notifications (no id) require no response.
    if method == "notifications/initialized" or request_id is None:
        return

    if method == "initialize":
        _result(request_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
        return

    if method == "ping":
        _result(request_id, {})
        return

    if method == "tools/list":
        _result(request_id, {"tools": TOOLS})
        return

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            text = _call_tool(name, arguments)
            _result(request_id, {"content": [{"type": "text", "text": text}]})
        except Exception as exc:  # noqa: BLE001 - report tool errors to the model
            _result(request_id, {
                "content": [{"type": "text", "text": f"Error: {exc}"}],
                "isError": True,
            })
        return

    _error(request_id, -32601, f"method not found: {method}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        try:
            _handle(message)
        except Exception as exc:  # noqa: BLE001 - never crash the loop
            request_id = message.get("id") if isinstance(message, dict) else None
            if request_id is not None:
                _error(request_id, -32603, f"internal error: {exc}")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        pass
