from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.models.conversations.conversation import Conversation, Message
from app.schemas.knowledge import RAGChatRequest, RAGChatResponse

router = APIRouter(prefix="/rag", tags=["RAG Chat"])


@router.post("/chat", response_model=RAGChatResponse)
async def rag_chat(payload: RAGChatRequest, db=Depends(get_db)) -> RAGChatResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="This RAG pipeline is deprecated. Use /ai/chat via the AI Router instead.",
    )


@router.get("/conversations/{conversation_id}/history")
async def get_conversation_history(conversation_id: str, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    try:
        from sqlalchemy import select

        conversation = await db.get(Conversation, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        stmt = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())
        result = await db.execute(stmt)
        messages = result.scalars().all()

        return {
            "conversation_id": conversation_id,
            "messages": [
                {
                    "id": str(msg.id),
                    "direction": msg.direction,
                    "channel": msg.channel,
                    "content": msg.content,
                    "is_ai_generated": msg.is_ai_generated,
                    "created_at": msg.created_at.isoformat(),
                }
                for msg in messages
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get history: {str(e)}")
