from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from app.analysis.services.conversation_analysis_service import ConversationAnalysisService
from app.analysis.services.event_bus import DomainEventPublisher, EVENT_CONVERSATION_ANALYSIS_REQUESTED
from app.database.session import SessionLocal
from app.models.conversations.conversation import Conversation
from loguru import logger
import uuid

router = APIRouter(prefix="/conversations", tags=["analysis"])

_analysis_service = ConversationAnalysisService()
_event_publisher = DomainEventPublisher(source="api")


class AnalyzeRequest(BaseModel):
    tenant_id: str = Field(..., description="Multi-tenant partition ID")
    conversation_id: str | None = Field(None, description="Existing conversation ID (creates one if omitted)")
    transcript: str | None = Field(None, description="Pre-existing conversation transcript")
    session_id: str | None = Field(None, description="Optional session tracking token")


class AnalyzeResponse(BaseModel):
    job_id: str
    conversation_id: str
    status: str = "queued"
    message: str = "Analysis request submitted. Results will be processed asynchronously."


class AnalysisResponse(BaseModel):
    conversation_id: str
    status: str
    sentiment: dict
    emotion: dict
    fusion: dict
    lead_score: dict
    claims: list[dict]
    verification: list[dict]
    summary: str | None
    speakers: list[dict]
    duration_seconds: int | None
    error_message: str | None


@router.post("/analyze", response_model=AnalyzeResponse, status_code=202)
async def analyze_conversation(request: AnalyzeRequest):
    if not request.transcript:
        raise HTTPException(status_code=400, detail="transcript is required for analysis")

    conv_id = request.conversation_id or str(uuid.uuid4())

    with SessionLocal() as session:
        existing = session.query(Conversation).filter(
            Conversation.id == conv_id, Conversation.tenant_id == request.tenant_id,
        ).first()
        if not existing:
            conv = Conversation(
                id=uuid.UUID(conv_id),
                tenant_id=uuid.UUID(request.tenant_id) if _is_uuid(request.tenant_id) else uuid.uuid4(),
                channel="api", status="active",
            )
            session.add(conv)
            session.commit()

    _analysis_service.create_analysis(conversation_id=conv_id, tenant_id=request.tenant_id)

    _event_publisher.publish(
        event_type=EVENT_CONVERSATION_ANALYSIS_REQUESTED,
        tenant_id=request.tenant_id,
        data={"conversation_id": conv_id, "tenant_id": request.tenant_id, "transcript": request.transcript, "session_id": request.session_id},
    )

    return AnalyzeResponse(job_id=conv_id, conversation_id=conv_id)


@router.post("/analyze/audio", response_model=AnalyzeResponse, status_code=202)
async def analyze_audio(tenant_id: str = Form(...), conversation_id: str = Form(None), audio: UploadFile = File(...)):
    import tempfile, os

    conv_id = conversation_id or str(uuid.uuid4())
    temp_dir = tempfile.gettempdir()
    audio_path = os.path.join(temp_dir, f"analysis_{conv_id}_{audio.filename}")
    with open(audio_path, "wb") as f:
        content = await audio.read()
        f.write(content)

    with SessionLocal() as session:
        existing = session.query(Conversation).filter(
            Conversation.id == conv_id, Conversation.tenant_id == tenant_id,
        ).first()
        if not existing:
            conv = Conversation(
                id=uuid.UUID(conv_id),
                tenant_id=uuid.UUID(tenant_id) if _is_uuid(tenant_id) else uuid.uuid4(),
                channel="api", status="active",
            )
            session.add(conv)
            session.commit()

    _analysis_service.create_analysis(conversation_id=conv_id, tenant_id=tenant_id)

    _event_publisher.publish(
        event_type=EVENT_CONVERSATION_ANALYSIS_REQUESTED,
        tenant_id=tenant_id,
        data={"conversation_id": conv_id, "tenant_id": tenant_id, "audio_path": audio_path},
    )

    return AnalyzeResponse(job_id=conv_id, conversation_id=conv_id)


@router.get("/{conversation_id}/analysis", response_model=AnalysisResponse)
async def get_analysis(conversation_id: str):
    record = _analysis_service.get_analysis(conversation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return AnalysisResponse(
        conversation_id=str(record.conversation_id),
        status=record.status,
        sentiment=record.sentiment,
        emotion=record.emotion,
        fusion=record.fusion,
        lead_score=record.lead_score,
        claims=record.claims,
        verification=record.verification,
        summary=record.summary,
        speakers=record.speakers,
        duration_seconds=record.duration_seconds,
        error_message=record.error_message,
    )


@router.get("/{conversation_id}/sentiment")
async def get_sentiment(conversation_id: str):
    record = _analysis_service.get_analysis(conversation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {"conversation_id": conversation_id, "sentiment": record.sentiment}


@router.get("/{conversation_id}/emotion")
async def get_emotion(conversation_id: str):
    record = _analysis_service.get_analysis(conversation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {"conversation_id": conversation_id, "emotion": record.emotion}


@router.get("/{conversation_id}/lead-score")
async def get_lead_score(conversation_id: str):
    record = _analysis_service.get_analysis(conversation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {"conversation_id": conversation_id, "lead_score": record.lead_score}


@router.get("/{conversation_id}/verified-insights")
async def get_verified_insights(conversation_id: str):
    record = _analysis_service.get_analysis(conversation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {"conversation_id": conversation_id, "claims": record.claims, "verification": record.verification}


def _is_uuid(val: str) -> bool:
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, AttributeError):
        return False
