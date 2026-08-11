from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config.settings import Settings
from app.core.security import create_access_token, get_authenticated_tenant_id
from app.routers.knowledge_query import get_knowledge_query_service, router
from app.services.knowledge.embedding_service import MistralEmbeddingService, embedding_model_name
from app.services.knowledge.llm_service import MistralLLMService
from app.services.knowledge.provider_errors import ProviderRateLimitError, ProviderTimeoutError
from app.services.knowledge.query_service import KnowledgeQueryService
from app.services.knowledge.retrieval_service import (
    KnowledgeRetrievalService,
    RetrievedChunk,
    assemble_context_prompt,
)


def settings(**overrides) -> Settings:
    values = {
        "MISTRAL_API_KEY": "test-key",
        "MISTRAL_EMBEDDING_MODEL": "shared-embedding-v1",
        "MISTRAL_CHAT_MODEL": "configured-chat-v1",
        "MISTRAL_API_BASE": "https://mistral.invalid/v1",
        "MISTRAL_EMBEDDING_BATCH_SIZE": 32,
        "QDRANT_VECTOR_SIZE": 3,
        "KNOWLEDGE_QUERY_TOP_K": 8,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.asyncio
async def test_embedding_batches_and_query_share_one_configured_model():
    request_batches: list[list[str]] = []
    request_models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        request_batches.append(body["input"])
        request_models.append(body["model"])
        return httpx.Response(200, json={
            "data": [
                {"index": index, "embedding": [float(index), 1.0, 0.0]}
                for index, _text in enumerate(body["input"])
            ]
        })

    configured = settings()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        service = MistralEmbeddingService(settings=configured, http_client=http)
        vectors = await service.embed_chunks([f"chunk-{index}" for index in range(65)])
        query_vector = await service.embed_query("pricing question")

    assert [len(batch) for batch in request_batches] == [22, 22, 21, 1]
    assert all(20 <= len(batch) <= 50 for batch in request_batches[:-1])
    assert len(vectors) == 65
    assert query_vector == [0.0, 1.0, 0.0]
    assert service.model == embedding_model_name(configured) == "shared-embedding-v1"
    assert set(request_models) == {"shared-embedding-v1"}


def test_every_qdrant_insert_gets_shared_embedding_model(monkeypatch):
    from app.services.rag.vectorstore import insert as insert_module

    captured = {}

    class Client:
        def upsert(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(insert_module, "get_qdrant", lambda: Client())
    monkeypatch.setattr(insert_module, "embedding_model_name", lambda: "shared-embedding-v1")
    monkeypatch.setattr(insert_module._settings, "QDRANT_VECTOR_SIZE", 3)
    insert_module.insert_chunks(
        [str(uuid4()), str(uuid4())],
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        [{"text": "one"}, {"text": "two", "embedding_model": "stale-model"}],
    )

    assert {point.payload["embedding_model"] for point in captured["points"]} == {"shared-embedding-v1"}


def test_qdrant_collection_dimension_mismatch_fails_before_workers_start(monkeypatch):
    from app.services.rag.vectorstore import qdrant as qdrant_module

    class Client:
        def get_collection(self, _name):
            return SimpleNamespace(
                config=SimpleNamespace(params=SimpleNamespace(vectors=SimpleNamespace(size=768)))
            )

    monkeypatch.setattr(qdrant_module, "get_qdrant", lambda: Client())
    monkeypatch.setattr(qdrant_module._settings, "QDRANT_COLLECTION_NAME", "wrong-size")
    monkeypatch.setattr(qdrant_module._settings, "QDRANT_VECTOR_SIZE", 1024)
    with pytest.raises(RuntimeError, match="has vector dimension 768"):
        qdrant_module.ensure_collection()


@pytest.mark.asyncio
async def test_llm_generate_streams_and_uses_configured_model():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        content = (
            'data: {"choices":[{"delta":{"content":"first "}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"second"}}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=content, headers={"content-type": "text/event-stream"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        service = MistralLLMService(settings=settings(), http_client=http)
        chunks = [value async for value in service.generate("Answer this", stream=True)]

    assert chunks == ["first ", "second"]
    assert requests == [{
        "model": "configured-chat-v1",
        "messages": [{"role": "user", "content": "Answer this"}],
        "stream": True,
    }]


class FixedEmbedder:
    async def embed_query(self, _text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


class CapturingLLM:
    def __init__(self):
        self.prompts: list[str] = []

    async def generate(self, prompt: str, stream: bool = True):
        self.prompts.append(prompt)
        yield "tenant-safe answer"


def qdrant_fixture():
    client = QdrantClient(":memory:")
    collection = f"retrieval_{uuid4().hex}"
    client.create_collection(collection, vectors_config=VectorParams(size=3, distance=Distance.COSINE))
    tenant_a, tenant_b = str(uuid4()), str(uuid4())
    source_a, source_b = str(uuid4()), str(uuid4())
    client.upsert(collection, points=[
        PointStruct(id=str(uuid4()), vector=[1.0, 0.0, 0.0], payload={
            "tenant_id": tenant_a, "approval_status": "approved", "category": "pricing",
            "text": "Enterprise price is 99.", "heading_path": ["Plans", "Enterprise"],
            "chunk_type": "table", "source_id": source_a,
        }),
        PointStruct(id=str(uuid4()), vector=[1.0, 0.0, 0.0], payload={
            "tenant_id": tenant_b, "approval_status": "approved", "category": "pricing",
            "text": "Enterprise price is 999999.", "heading_path": ["Plans", "Enterprise"],
            "chunk_type": "table", "source_id": source_b,
        }),
        PointStruct(id=str(uuid4()), vector=[1.0, 0.0, 0.0], payload={
            "tenant_id": tenant_a, "approval_status": "approved", "category": "faqs",
            "text": "A different category.", "heading_path": ["FAQs"],
            "chunk_type": "faq", "source_id": source_a,
        }),
    ])
    return client, collection, tenant_a, tenant_b, source_a


@pytest.mark.asyncio
async def test_search_executes_tenant_and_optional_category_isolation():
    qdrant, collection, tenant_a, _tenant_b, source_a = qdrant_fixture()
    service = KnowledgeRetrievalService(
        qdrant=qdrant, embedder=FixedEmbedder(), settings=settings(), collection_name=collection
    )

    results = await service.search("enterprise price", tenant_a, category="pricing", top_k=8)

    assert len(results) == 1
    assert results[0].tenant_id == tenant_a
    assert results[0].source_id == source_a
    assert results[0].heading_path == ["Plans", "Enterprise"]
    assert results[0].chunk_type == "table"
    assert "999999" not in results[0].text

    without_category = await service.search("enterprise price", tenant_a, top_k=8)
    assert {chunk.category for chunk in without_category} == {"pricing", "faqs"}
    assert all(chunk.tenant_id == tenant_a for chunk in without_category)
    assert all("999999" not in chunk.text for chunk in without_category)


def test_context_prompt_includes_heading_and_structural_provenance():
    prompt = assemble_context_prompt("What is the price?", [RetrievedChunk(
        chunk_id="chunk-a", text="Enterprise is 99.", score=1.0, tenant_id="tenant-a",
        category="pricing", heading_path=["Plans", "Enterprise"], chunk_type="table", source_id="source-a",
    )])

    assert "Heading path: Plans > Enterprise" in prompt
    assert "Source ID: source-a" in prompt
    assert "Chunk type: table" in prompt
    assert "Answer only from the supplied evidence" in prompt


def query_app(tenant_id: str | None, service: KnowledgeQueryService) -> FastAPI:
    api = FastAPI()
    api.include_router(router)
    if tenant_id is not None:
        api.dependency_overrides[get_authenticated_tenant_id] = lambda: tenant_id
    api.dependency_overrides[get_knowledge_query_service] = lambda: service
    return api


def test_query_endpoint_executes_same_tenant_boundary_and_hides_tenant_id():
    qdrant, collection, tenant_a, _tenant_b, source_a = qdrant_fixture()
    llm = CapturingLLM()
    service = KnowledgeQueryService(
        retrieval=KnowledgeRetrievalService(
            qdrant=qdrant, embedder=FixedEmbedder(), settings=settings(), collection_name=collection
        ),
        llm=llm,
        settings=settings(),
    )
    token = create_access_token(user_id=uuid4(), tenant_id=UUID(tenant_a))
    response = TestClient(query_app(None, service)).post(
        "/api/v1/knowledge/query",
        json={"query": "enterprise price", "category": "pricing"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert source_a in response.text
    assert "999999" not in response.text
    assert "999999" not in llm.prompts[0]
    assert tenant_a not in response.text

    rejected = TestClient(query_app(None, service)).post(
        "/api/v1/knowledge/query",
        json={"query": "enterprise price", "tenant_id": str(uuid4())},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rejected.status_code == 422


class SlowLLM:
    def __init__(self, release: threading.Event, completed: threading.Event):
        self.release = release
        self.completed = completed

    async def generate(self, _prompt: str, stream: bool = True):
        yield "first"
        while not self.release.is_set():
            await asyncio.sleep(0.01)
        self.completed.set()
        yield "last"


class StaticRetrieval:
    async def search(self, *_args, **_kwargs):
        return [RetrievedChunk(
            chunk_id="chunk-a", text="Known fact", score=1.0, tenant_id="tenant-a",
            category="pricing", heading_path=["Pricing"], chunk_type="prose", source_id="source-a",
        )]


def _free_port() -> int:
    with socket.socket() as value:
        value.bind(("127.0.0.1", 0))
        return value.getsockname()[1]


def test_query_endpoint_sends_first_answer_bytes_before_generation_completes():
    release, completed = threading.Event(), threading.Event()
    service = KnowledgeQueryService(retrieval=StaticRetrieval(), llm=SlowLLM(release, completed), settings=settings())
    api = query_app(str(uuid4()), service)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(api, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started

    try:
        with httpx.Client(timeout=5).stream(
            "POST", f"http://127.0.0.1:{port}/api/v1/knowledge/query", json={"query": "price"}
        ) as response:
            lines = iter(response.iter_lines())
            for line in lines:
                if line == "event: token":
                    assert json.loads(next(lines).removeprefix("data: ")) == {"text": "first"}
                    break
            else:
                pytest.fail("No streamed token event arrived")
            assert completed.is_set() is False
            release.set()
            remaining = "\n".join(lines)
            assert '"text":"last"' in remaining
            assert completed.is_set() is True
    finally:
        release.set()
        server.should_exit = True
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_embedding_rate_limit_is_a_clean_typed_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "private provider detail"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        service = MistralEmbeddingService(settings=settings(), http_client=http)
        with pytest.raises(ProviderRateLimitError) as raised:
            await service.embed_query("question")
    assert "private provider detail" not in raised.value.public_message


@pytest.mark.asyncio
async def test_generation_timeout_is_a_clean_typed_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private provider detail", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        service = MistralLLMService(settings=settings(), http_client=http)
        with pytest.raises(ProviderTimeoutError) as raised:
            _chunks = [value async for value in service.generate("question", stream=True)]
    assert "private provider detail" not in raised.value.public_message


class RateLimitedRetrieval:
    async def search(self, *_args, **_kwargs):
        raise ProviderRateLimitError()


class TimeoutLLM:
    async def generate(self, *_args, **_kwargs):
        raise ProviderTimeoutError()
        yield  # pragma: no cover


def test_endpoint_returns_clean_rate_limit_and_stream_timeout_errors():
    tenant_id = str(uuid4())
    limited = KnowledgeQueryService(retrieval=RateLimitedRetrieval(), llm=CapturingLLM(), settings=settings())
    response = TestClient(query_app(tenant_id, limited)).post(
        "/api/v1/knowledge/query", json={"query": "price"}
    )
    assert response.status_code == 429
    assert response.json()["detail"] == {
        "code": "provider_rate_limited",
        "message": "The AI provider is temporarily rate limited. Please retry shortly.",
        "retryable": True,
    }

    timed_out = KnowledgeQueryService(retrieval=StaticRetrieval(), llm=TimeoutLLM(), settings=settings())
    response = TestClient(query_app(tenant_id, timed_out)).post(
        "/api/v1/knowledge/query", json={"query": "price"}
    )
    assert response.status_code == 200
    assert "event: error" in response.text
    assert "provider_timeout" in response.text
    assert "private provider detail" not in response.text


def test_query_route_is_mounted_and_tenant_is_not_a_request_field():
    from app.main import create_app

    schema = create_app().openapi()
    operation = schema["paths"]["/api/v1/knowledge/query"]["post"]
    body_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    request_schema = schema["components"]["schemas"][body_schema["$ref"].rsplit("/", 1)[-1]]
    assert set(request_schema["properties"]) == {"query", "category", "top_k"}
    assert operation["security"]
