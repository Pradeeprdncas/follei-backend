"""Bounded public-web crawler for tenant knowledge ingestion."""
from __future__ import annotations

import ipaddress
import socket
from collections import deque
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import aiohttp
from aiohttp.abc import AbstractResolver
from bs4 import BeautifulSoup

USER_AGENT = "FolleiKnowledgeBot/1.0"
MAX_PAGE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 5_000_000
DOWNLOADABLE_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls", ".csv", ".ppt", ".pptx", ".txt", ".eml", ".msg"}


class _PinnedResolver(AbstractResolver):
    """Resolve the crawl host only to addresses validated before the request."""

    def __init__(self, hostname: str, addresses: list[str]):
        self.hostname = hostname
        self.addresses = addresses

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET):
        if host.lower().rstrip(".") != self.hostname:
            raise OSError("Crawler DNS resolver rejected an unexpected host")
        return [
            {
                "hostname": host,
                "host": value,
                "port": port,
                "family": socket.AF_INET6 if ":" in value else socket.AF_INET,
                "proto": 0,
                "flags": 0,
            }
            for value in self.addresses
        ]

    async def close(self):
        return None


def _public_addresses(hostname: str) -> list[str]:
    addresses = {row[4][0] for row in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)}
    if not addresses:
        raise ValueError("Website host did not resolve")
    for value in addresses:
        address = ipaddress.ip_address(value)
        if not address.is_global:
            raise ValueError("Website host resolves to a private or non-public address")
    return sorted(addresses)


def validate_public_url(url: str, *, expected_host: str | None = None) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTP(S) URLs without embedded credentials are allowed")
    host = parsed.hostname.lower().rstrip(".")
    if expected_host and host != expected_host:
        raise ValueError("Crawler may not leave the submitted domain")
    _public_addresses(host)
    return host


def _extract_page(url: str, html: str) -> tuple[dict, list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else url
    lines = []
    for node in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "th", "td"]):
        value = node.get_text(" ", strip=True)
        if value:
            prefix = "#" * int(node.name[1]) + " " if node.name.startswith("h") else ""
            lines.append(prefix + value)
    links = [urldefrag(urljoin(url, anchor.get("href")))[0] for anchor in soup.find_all("a", href=True)]
    return {"url": url, "title": title, "text": "\n".join(lines)}, links


async def _crawl_rendered(url: str, *, max_pages: int, root_host: str, root_addresses: list[str], robots: RobotFileParser) -> list[dict]:
    """Render JavaScript-only pages without relaxing crawler safety bounds."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return []

    pages: list[dict] = []
    seen: set[str] = set()
    queue = deque([urldefrag(url)[0]])
    total_bytes = 0
    async with async_playwright() as playwright:
        pinned = next((value for value in root_addresses if ":" not in value), root_addresses[0])
        browser = await playwright.chromium.launch(
            headless=True,
            args=[f"--host-resolver-rules=MAP {root_host} {pinned}, EXCLUDE localhost"],
        )
        context = await browser.new_context(user_agent=USER_AGENT)

        async def bounded_request(route, request):
            parsed = urlparse(request.url)
            if parsed.scheme in {"about", "blob", "data"}:
                await route.continue_()
                return
            try:
                validate_public_url(request.url, expected_host=root_host)
            except ValueError:
                await route.abort()
                return
            await route.continue_()

        await context.route("**/*", bounded_request)
        page = await context.new_page()
        try:
            while queue and len(pages) < max_pages and total_bytes < MAX_TOTAL_BYTES:
                current = queue.popleft()
                if current in seen or not robots.can_fetch(USER_AGENT, current):
                    continue
                validate_public_url(current, expected_host=root_host)
                seen.add(current)
                try:
                    response = await page.goto(current, wait_until="domcontentloaded", timeout=15_000)
                    if response and response.status >= 400:
                        continue
                    await page.wait_for_timeout(1_500)
                    html = await page.content()
                except Exception:
                    continue
                final_url = urldefrag(page.url)[0]
                try:
                    validate_public_url(final_url, expected_host=root_host)
                except ValueError:
                    continue
                seen.add(final_url)
                encoded = html.encode("utf-8")
                if len(encoded) > MAX_PAGE_BYTES or total_bytes + len(encoded) > MAX_TOTAL_BYTES:
                    continue
                total_bytes += len(encoded)
                extracted, links = _extract_page(final_url, html)
                if extracted["text"].strip():
                    pages.append(extracted)
                for link in links:
                    try:
                        validate_public_url(link, expected_host=root_host)
                    except ValueError:
                        continue
                    if link not in seen:
                        queue.append(link)
        finally:
            await context.close()
            await browser.close()
    return pages


async def crawl_website(url: str, *, max_pages: int = 25, include_assets: bool = False) -> list[dict]:
    """Crawl HTML pages and, optionally, same-site documents within existing bounds."""
    max_pages = max(1, min(max_pages, 25))
    root_host = validate_public_url(url)
    root_addresses = _public_addresses(root_host)
    timeout = aiohttp.ClientTimeout(total=20, connect=5, sock_read=10)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    pages, seen, queue, total_bytes = [], set(), deque([urldefrag(url)[0]]), 0
    assets: list[dict] = []
    asset_urls: set[str] = set()
    connector = aiohttp.TCPConnector(resolver=_PinnedResolver(root_host, root_addresses))
    async with aiohttp.ClientSession(timeout=timeout, headers=headers, connector=connector) as session:
        robots = RobotFileParser()
        robots.set_url(urljoin(url, "/robots.txt"))
        try:
            validate_public_url(robots.url, expected_host=root_host)
            async with session.get(robots.url, allow_redirects=False) as response:
                robots.parse((await response.text(errors="replace")).splitlines() if response.status == 200 else [])
        except (aiohttp.ClientError, TimeoutError):
            robots.parse([])
        while queue and len(pages) < max_pages and total_bytes < MAX_TOTAL_BYTES:
            current = queue.popleft()
            if current in seen:
                continue
            validate_public_url(current, expected_host=root_host)
            if not robots.can_fetch(USER_AGENT, current):
                continue
            seen.add(current)
            for _ in range(5):
                async with session.get(current, allow_redirects=False) as response:
                    if 300 <= response.status < 400 and response.headers.get("Location"):
                        current = urljoin(current, response.headers["Location"])
                        validate_public_url(current, expected_host=root_host)
                        continue
                    if response.status != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
                        break
                    body = await response.content.read(MAX_PAGE_BYTES + 1)
                    if len(body) > MAX_PAGE_BYTES:
                        break
                    total_bytes += len(body)
                    page, links = _extract_page(current, body.decode(response.charset or "utf-8", errors="replace"))
                    if page["text"].strip():
                        pages.append(page)
                    for link in links:
                        try:
                            validate_public_url(link, expected_host=root_host)
                        except ValueError:
                            continue
                        suffix = Path(urlparse(link).path).suffix.lower()
                        if include_assets and suffix in DOWNLOADABLE_EXTENSIONS and link not in asset_urls:
                            asset_urls.add(link)
                            try:
                                async with session.get(link, allow_redirects=False) as asset_response:
                                    content_type = asset_response.headers.get("Content-Type", "").lower()
                                    if asset_response.status == 200 and "text/html" not in content_type:
                                        content = await asset_response.content.read(MAX_PAGE_BYTES + 1)
                                        if len(content) <= MAX_PAGE_BYTES and total_bytes + len(content) <= MAX_TOTAL_BYTES:
                                            total_bytes += len(content)
                                            assets.append({"url": link, "title": Path(urlparse(link).path).name or "website-asset", "filename": Path(urlparse(link).path).name or f"website-asset{suffix}", "file_type": suffix.lstrip("."), "content": content})
                            except (aiohttp.ClientError, TimeoutError):
                                pass
                        elif link not in seen:
                            queue.append(link)
                    break
    if pages:
        return pages + assets
    rendered = await _crawl_rendered(url, max_pages=max_pages, root_host=root_host, root_addresses=root_addresses, robots=robots)
    return rendered + assets
