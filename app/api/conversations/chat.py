from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from app.services.rag.pipelines.chat import chat_pipeline
from loguru import logger

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(..., description="The raw natural language query from the user, typos included.")
    tenant_id: str = Field(..., description="Unique partition identifier for multi-tenant data access control.")
    session_id: str | None = Field(None, description="Optional conversation tracking token for state keeping.")


class ChatResponse(BaseModel):
    answer: str = Field(..., description="The generated engineering response, or fallback warning text.")
    citations: list[dict] = Field(default=[], description="Source document structural metadata pointers.")
    confidence: float = Field(..., description="Evaluation matching metric scale from 0.0 to 1.0.")
    supported: bool = Field(..., description="True if truth claims perfectly match the database context chunks.")
    reason: str = Field(..., description="System diagnostic overview details from the verification engine.")
    conversation_id: str | None = Field(None, description="Persistent conversation identifier for multi-turn state tracking.")


@router.post("/", response_model=ChatResponse, status_code=status.HTTP_200_OK, summary="Submit query to Verified RAG Pipeline")
async def chat(request: ChatRequest):
    if not request.question.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question argument parameter cannot consist of empty whitespace values.")

    try:
        result = await chat_pipeline(question=request.question, tenant_id=request.tenant_id, session_id=request.session_id)
        return ChatResponse(**result)
    except Exception as e:
        logger.error(f"Fatal error sequence encountered inside Chat Pipeline Interface: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal system RAG workflow pipeline exception error: {str(e)}")
