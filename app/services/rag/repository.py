import re
import hashlib
from uuid import UUID
from typing import Any

from qdrant_client.http.models import (
    SparseVectorParams, SparseIndexParams, VectorParams, Distance,
    PointStruct, SparseVector, Filter, FieldCondition, MatchValue,
    HasIdCondition, SearchRequest, HnswConfigDiff, OptimizersConfigDiff,
)
from loguru import logger

from app.config.qdrant import get_qdrant
from app.config.settings import get_settings
from app.services.rag.embeddings.local import embed_texts, embed_query

_settings = get_settings()
COLLECTION = _settings.QDRANT_COLLECTION_NAME
VECTOR_SIZE = _settings.QDRANT_VECTOR_SIZE
SPARSE_DIM = 2048
DEFAULT_TOP_K = _settings.TOP_K_RETRIEVAL


def _text_to_sparse(text: str) -> tuple[list[int], list[float]]:
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    if not words:
        return [], []
    tf: dict[str, float] = {}
    for w in words:
        tf[w] = tf.get(w, 0.0) + 1.0
    max_f = max(tf.values())
    indices: list[int] = []
    values: list[float] = []
    for w, c in tf.items():
        idx = int(hashlib.md5(w.encode()).hexdigest(), 16) % SPARSE_DIM
        indices.append(idx)
        values.append(c / max_f)
    return indices, values


def _tenant_filter(tenant_id: str) -> Filter | None:
    if not tenant_id:
        return None
    return Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))])


class RagRepository:
    """Qdrant repository for chunk CRUD and hybrid search.

    Single collection with tenant_id payload filter (not per-tenant collections).
    Supports dense + sparse hybrid search via Qdrant's native sparse vectors.
    """

    def __init__(self) -> None:
        self._client = get_qdrant()
        self._collection = COLLECTION
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        try:
            existing = self._client.get_collection(self._collection)
            logger.info("Qdrant collection '{}' ready (dim={})", self._collection,
                        existing.config.params.vectors.size)
            return
        except Exception:
            pass
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            sparse_vectors_config={
                "sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False)),
            },
            hnsw_config=HnswConfigDiff(
                m=16,
                ef_construct=100,
                full_scan_threshold=10000,
            ),
            optimizers_config=OptimizersConfigDiff(
                default_segment_number=2,
            ),
        )
        for field in ("tenant_id", "document_id", "knowledge_scope", "source_kind"):
            try:
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name=field,
                    field_schema={"type": "keyword"},
                )
            except Exception:
                pass
        logger.info("Qdrant collection '{}' ready (dense={}d, sparse={}d)", self._collection, VECTOR_SIZE, SPARSE_DIM)

    # â”€â”€ CRUD â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def upsert_chunks(
        self,
        chunk_ids: list[str],
        dense_vectors: list[list[float]],
        payloads: list[dict],
    ) -> int:
        if not chunk_ids:
            return 0
        points: list[PointStruct] = []
        for cid, vec, p in zip(chunk_ids, dense_vectors, payloads):
            text = p.get("text") or p.get("content") or ""
            sparse_idx, sparse_val = _text_to_sparse(text)
            points.append(PointStruct(
                id=cid,
                vector={"dense": vec, "sparse": SparseVector(indices=sparse_idx, values=sparse_val)},
                payload=p,
            ))
        self._client.upsert(collection_name=self._collection, points=points)
        logger.info("Upserted {} chunks to Qdrant", len(points))
        return len(points)

    def delete_chunks(self, document_id: str, tenant_id: str) -> int:
        qfilter = Filter(must=[
            FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
            FieldCondition(key="document_id", match=MatchValue(value=document_id)),
        ])
        result = self._client.delete(
            collection_name=self._collection,
            points_selector=qfilter,
        )
        count = getattr(result, "count", 0)
        logger.info("Deleted {} chunks for document={} tenant={}", count, document_id, tenant_id)
        return count

    def delete_tenant_chunks(self, tenant_id: str) -> int:
        qfilter = _tenant_filter(tenant_id)
        if qfilter is None:
            return 0
        result = self._client.delete(
            collection_name=self._collection,
            points_selector=qfilter,
        )
        count = getattr(result, "count", 0)
        logger.info("Deleted all chunks for tenant={}", tenant_id)
        return count

    # â”€â”€ Hybrid Search â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def hybrid_search(
        self,
        dense_vector: list[float],
        sparse_indices: list[int],
        sparse_values: list[float],
        tenant_id: str,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        k = top_k or DEFAULT_TOP_K
        qfilter = _tenant_filter(tenant_id)

        try:
            response = self._client.search(
                collection_name=self._collection,
                query_vector=("dense", dense_vector),
                query_filter=qfilter,
                limit=k,
                with_payload=True,
            )
        except Exception:
            response = self._client.query_points(
                collection_name=self._collection,
                query=dense_vector,
                query_filter={"must": [{"key": "tenant_id", "match": {"value": tenant_id}}]} if tenant_id else None,
                limit=k,
                with_payload=True,
            ).points

        results = []
        for point in response:
            payload = point.payload or {}
            results.append({
                "chunk_id": str(point.id),
                "score": point.score,
                "text": payload.get("text", "") or payload.get("content", ""),
                "page": payload.get("page"),
                "heading": payload.get("heading"),
                "chunk_index": payload.get("chunk_index", 0),
                "document_id": payload.get("document_id"),
                "payload": payload,
            })
        return results

    def dense_search(
        self,
        dense_vector: list[float],
        tenant_id: str,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        return self.hybrid_search(dense_vector, [], [], tenant_id, top_k)

    def count_chunks(self, tenant_id: str | None = None) -> int:
        qfilter = _tenant_filter(tenant_id) if tenant_id else None
        result = self._client.count(
            collection_name=self._collection,
            count_filter=qfilter,
        )
        return result.count


_repo: RagRepository | None = None


def get_rag_repository() -> RagRepository:
    global _repo
    if _repo is None:
        _repo = RagRepository()
    return _repo


