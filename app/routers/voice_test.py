"""Local live-voice test page.

Serves a static browser page (mic in -> /ws/voice -> reply out) and a
bootstrap endpoint that creates a real Tenant + Lead + Conversation row so a
fresh visit can start speaking immediately -- the voice pipeline's score
persistence (app/api/websocket_handler.py -> ConversationAnalysisService /
app/workers/lead_scoring_worker.py) requires a real Conversation row to
attach to via a foreign key, and a real Lead to write scores onto.

Test/demo tooling only -- not part of the tenant-facing product surface.
"""
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.database.session import SessionLocal
from app.models.conversations.conversation import Conversation
from app.models.leads.lead import Lead
from app.models.tenancy import Tenant

router = APIRouter(tags=["Voice Test"])

_PAGE_PATH = Path(__file__).resolve().parent.parent / "static" / "voice_test.html"


@router.get("/voice-test")
def voice_test_page() -> FileResponse:
    return FileResponse(_PAGE_PATH)


class VoiceTestSessionResponse(BaseModel):
    tenant_id: str
    lead_id: str
    conversation_id: str


@router.post("/voice-test/session", response_model=VoiceTestSessionResponse)
def create_voice_test_session() -> VoiceTestSessionResponse:
    with SessionLocal() as db:
        tenant = Tenant(id=uuid4(), name="Voice Test Tenant")
        db.add(tenant)
        db.flush()

        lead = Lead(
            id=uuid4(),
            tenant_id=tenant.id,
            email=f"voice-test-{tenant.id}@example.com",
            first_name="Voice",
            last_name="Tester",
            company="Voice Test Co",
        )
        db.add(lead)
        db.flush()

        conversation = Conversation(
            id=uuid4(),
            tenant_id=tenant.id,
            lead_id=lead.id,
            channel="voice",
            status="active",
        )
        db.add(conversation)
        db.commit()

        return VoiceTestSessionResponse(
            tenant_id=str(tenant.id),
            lead_id=str(lead.id),
            conversation_id=str(conversation.id),
        )
