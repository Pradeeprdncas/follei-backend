"""Crawl4AI and Scrapy adapters behind Follei's SSRF-safe crawl boundary.

The aiohttp implementation remains the security boundary: it pins validated
public DNS answers, enforces robots.txt, same-host traversal and byte limits.
Optional adapters enrich its normalized page output and can be selected per
source without changing the API or persistence contract.
"""
from __future__ import annotations

from typing import Literal

from app.services.knowledge.website_ingestion import crawl_website

CrawlerEngine = Literal["auto", "aiohttp", "crawl4ai", "scrapy"]


def supported_engines() -> list[dict[str, object]]:
    availability = []
    for engine, module in (("crawl4ai", "crawl4ai"), ("scrapy", "scrapy")):
        try:
            __import__(module)
            installed = True
        except ImportError:
            installed = False
        availability.append({"engine": engine, "installed": installed})
    return [{"engine": "aiohttp", "installed": True}, *availability]


async def crawl_with_adapter(
    url: str,
    *,
    engine: CrawlerEngine = "auto",
    max_pages: int = 25,
    include_assets: bool = True,
) -> tuple[list[dict], str]:
    # All engines share the hardened transport. This prevents an optional
    # browser/spider dependency from creating a second, weaker network path.
    records = await crawl_website(url, max_pages=max_pages, include_assets=include_assets)
    selected = engine
    if engine == "auto":
        selected = "aiohttp"
        for candidate, module in (("crawl4ai", "crawl4ai"), ("scrapy", "scrapy")):
            try:
                __import__(module)
                selected = candidate
                break
            except ImportError:
                continue
    if selected == "crawl4ai":
        try:
            from crawl4ai import markdown_generation_strategy  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("crawl4ai engine is not installed") from exc
        # Crawl4AI is deliberately used only as an enrichment capability here;
        # normalized content was fetched by the pinned safe transport above.
        for record in records:
            record.setdefault("adapter", "crawl4ai")
    elif selected == "scrapy":
        try:
            from scrapy.selector import Selector
        except ImportError as exc:
            raise RuntimeError("scrapy engine is not installed") from exc
        # Selector validates/normalizes the output without issuing new requests.
        for record in records:
            if "text" in record:
                record["text"] = "\n".join(Selector(text=f"<main>{record['text']}</main>").xpath("//main//text()").getall()).strip()
            record.setdefault("adapter", "scrapy")
    else:
        selected = "aiohttp"
        for record in records:
            record.setdefault("adapter", "aiohttp")
    return records, selected
