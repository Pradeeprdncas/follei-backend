from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from loguru import logger
import time

from app.services.ai.model_manager import get_model_manager
from app.services.ai.services.readiness import get_readiness_service

router = APIRouter(prefix="/ai", tags=["AI"])


class EmbedRequest(BaseModel):
    texts: List[str] = Field(..., min_length=1, max_length=100)
    normalize: bool = True


class EmbedResponse(BaseModel):
    embeddings: List[List[float]]
    model: str
    latency_ms: float


class ClassifyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    categories: Optional[List[str]] = None


class ClassifyResponse(BaseModel):
    category: str
    confidence: float
    all_scores: Dict[str, float]


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=50000)
    max_tokens: int = Field(512, ge=1, le=4096)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    top_p: float = Field(0.9, ge=0.0, le=1.0)


class GenerateResponse(BaseModel):
    text: str
    model: str
    tokens_generated: int
    latency_ms: float


class SummarizeRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=50000)
    max_length: int = Field(256, ge=50, le=1024)
    min_length: int = Field(50, ge=10, le=512)


class SummarizeResponse(BaseModel):
    summary: str
    original_length: int
    summary_length: int
    compression_ratio: float


class RewriteQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    context: Optional[str] = None


class RewriteQueryResponse(BaseModel):
    rewritten_query: str
    original_query: str


class RerankRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    documents: List[str] = Field(..., min_length=1, max_length=100)
    top_k: int = Field(5, ge=1, le=20)


class RerankResponse(BaseModel):
    ranked_documents: List[Dict[str, Any]]
    scores: List[float]


class VerifyRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    answer: str = Field(..., min_length=1, max_length=10000)


class VerifyResponse(BaseModel):
    verified: bool
    confidence: float
    explanation: str


class PlanRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=10000)


class PlanResponse(BaseModel):
    goal: str
    steps: List[str]
    plan: str


def _check_ready():
    readiness = get_readiness_service()
    if not readiness.is_ready():
        raise HTTPException(status_code=503, detail="AI runtime not ready")


@router.post("/embed", response_model=EmbedResponse)
async def embed(request: EmbedRequest):
    _check_ready()
    start = time.time()
    try:
        manager = get_model_manager()
        model_info = await manager.get_model("embedding", "nomic-embed-text-v1.5")
        loader = model_info["loader"]
        result = await loader.encode(request.texts, normalize=request.normalize)
        latency = (time.time() - start) * 1000
        return EmbedResponse(embeddings=result, model="nomic-embed-text-v1.5", latency_ms=round(latency, 2))
    except Exception as e:
        logger.error(f"Embed failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/classify", response_model=ClassifyResponse)
async def classify(request: ClassifyRequest):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Classifier model type is not available in the current configuration.")


@router.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest):
    _check_ready()
    start = time.time()
    try:
        manager = get_model_manager()
        model_info = await manager.get_model("generator", "qwen2.5-3b-instruct")
        loader = model_info["loader"]
        result = await loader.infer(request.prompt, max_new_tokens=request.max_tokens, temperature=request.temperature, top_p=request.top_p)
        latency = (time.time() - start) * 1000

        if isinstance(result, str):
            text = result
            tokens = len(text.split())
        else:
            text = result.get("text", "")
            tokens = result.get("tokens_generated", len(text.split()))

        return GenerateResponse(text=text, model="qwen2.5-3B-Instruct", tokens_generated=tokens, latency_ms=round(latency, 2))
    except Exception as e:
        logger.error(f"Generate failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize(request: SummarizeRequest):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Summarizer model type is not available in the current configuration.")


@router.post("/rewrite-query", response_model=RewriteQueryResponse)
async def rewrite_query(request: RewriteQueryRequest):
    _check_ready()
    start = time.time()
    try:
        manager = get_model_manager()
        model_info = await manager.get_model("query_optimizer", "qwen2.5-0.5b")
        loader = model_info["loader"]
        result = await loader.infer(request.query, context=request.context)
        latency = (time.time() - start) * 1000
        return RewriteQueryResponse(rewritten_query=result.get("rewritten_query", request.query), original_query=request.query)
    except Exception as e:
        logger.error(f"Rewrite query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rerank", response_model=RerankResponse)
async def rerank(request: RerankRequest):
    _check_ready()
    start = time.time()
    try:
        manager = get_model_manager()
        model_info = await manager.get_model("reranker", "bge-reranker-base")
        loader = model_info["loader"]
        result = await loader.rerank(request.query, request.documents, top_k=request.top_k)
        latency = (time.time() - start) * 1000
        return RerankResponse(ranked_documents=result.get("ranked_documents", []), scores=result.get("scores", []))
    except Exception as e:
        logger.error(f"Rerank failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify", response_model=VerifyResponse)
async def verify(request: VerifyRequest):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Verifier model type is not available in the current configuration.")


@router.post("/plan", response_model=PlanResponse)
async def plan(request: PlanRequest):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Planner model type is not available in the current configuration.")
