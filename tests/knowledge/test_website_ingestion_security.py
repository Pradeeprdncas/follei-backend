import pytest
from app.services.knowledge import website_ingestion
from app.services.knowledge.crawlers import registry


def test_rejects_private_resolved_address(monkeypatch):
    monkeypatch.setattr(website_ingestion.socket, "getaddrinfo", lambda *_a, **_k: [(None, None, None, None, ("127.0.0.1", 0))])
    with pytest.raises(ValueError, match="private or non-public"):
        website_ingestion.validate_public_url("http://example.com")


def test_rejects_credentials_and_cross_domain(monkeypatch):
    monkeypatch.setattr(website_ingestion, "_public_addresses", lambda _host: ["93.184.216.34"])
    with pytest.raises(ValueError, match="credentials"):
        website_ingestion.validate_public_url("https://user:pass@example.com")
    with pytest.raises(ValueError, match="leave"):
        website_ingestion.validate_public_url("https://other.example/page", expected_host="example.com")


def test_extracts_heading_text_and_same_page_links():
    page, links = website_ingestion._extract_page("https://example.com/", "<title>Acme</title><h1>Pricing</h1><p>Enterprise is USD 999.</p><a href='/policy'>Policy</a><script>secret()</script>")
    assert page["title"] == "Acme"
    assert "# Pricing" in page["text"]
    assert "Enterprise is USD 999." in page["text"]
    assert "secret" not in page["text"]
    assert links == ["https://example.com/policy"]


@pytest.mark.asyncio
async def test_crawl_initializes_total_byte_counter_and_returns_page(monkeypatch):
    class _Content:
        async def read(self, _limit):
            return b"<title>Acme</title><h1>Pricing</h1><p>Enterprise is USD 999.</p>"

    class _Response:
        status = 200
        headers = {"Content-Type": "text/html; charset=utf-8"}
        charset = "utf-8"
        content = _Content()

        async def text(self, **_kwargs):
            return ""

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def get(self, *_args, **_kwargs):
            return _Response()

    monkeypatch.setattr(website_ingestion, "_public_addresses", lambda _host: ["93.184.216.34"])
    monkeypatch.setattr(website_ingestion.aiohttp, "ClientSession", lambda **_kwargs: _Session())

    pages = await website_ingestion.crawl_website("https://example.com/", max_pages=1)

    assert pages == [{"url": "https://example.com/", "title": "Acme", "text": "# Pricing\nEnterprise is USD 999."}]


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", ["aiohttp", "crawl4ai", "scrapy"])
async def test_every_engine_preserves_ssrf_rejection(engine):
    with pytest.raises(ValueError, match="private or non-public"):
        await registry.crawl_with_adapter("http://127.0.0.1/", engine=engine)


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", ["aiohttp", "crawl4ai", "scrapy"])
@pytest.mark.parametrize(
    ("error", "message"),
    [
        (PermissionError("robots.txt disallows this crawl"), "robots.txt"),
        (ValueError("Crawl attempted to leave the verified domain"), "leave the verified domain"),
    ],
)
async def test_every_engine_preserves_common_crawl_policy(monkeypatch, engine, error, message):
    async def reject_before_adapter(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(registry, "crawl_website", reject_before_adapter)

    with pytest.raises(type(error), match=message):
        await registry.crawl_with_adapter("https://example.com/", engine=engine)
