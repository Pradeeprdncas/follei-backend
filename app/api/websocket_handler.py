"""Native WebSocket handler for real-time conversation, voice, and analysis streaming."""
import asyncio
import base64
import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from loguru import logger
import numpy as np

from app.events.publisher import DomainEventPublisher
from app.events.base import (
    EVENT_INTERACTION_CREATED,
    EVENT_INTERACTION_ANALYSIS_REQUESTED,
    EVENT_MESSAGE_ADDED,
)
from app.analysis.services.event_bus import EVENT_CONVERSATION_ANALYSIS_COMPLETED
from app.services.rag.filler_service import generate_filler

router = APIRouter()
publisher = DomainEventPublisher(source="websocket")
_SPOKEN_SOURCE_RE = re.compile(r"\[Source:[^\]]+\]", re.IGNORECASE)


class ConnectionManager:
    """Manages WebSocket connections grouped by conversation."""

    def __init__(self):
        self._rooms: dict[str, set[WebSocket]] = {}

    async def connect(self, conversation_id: str, ws: WebSocket):
        await ws.accept()
        self._rooms.setdefault(conversation_id, set()).add(ws)
        logger.info(f"WS connected: conversation={conversation_id} connections={len(self._rooms[conversation_id])}")

    def disconnect(self, conversation_id: str, ws: WebSocket):
        room = self._rooms.get(conversation_id)
        if room:
            room.discard(ws)
            if not room:
                del self._rooms[conversation_id]

    async def broadcast(self, conversation_id: str, message: dict):
        room = self._rooms.get(conversation_id, set())
        dead = set()
        for ws in room:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            room.discard(ws)

    async def send_to(self, ws: WebSocket, message: dict):
        try:
            await ws.send_json(message)
        except Exception as e:
            logger.error(f"WS send error: {e}")


manager = ConnectionManager()


@router.websocket("/ws/conversation/{conversation_id}")
async def conversation_ws(
    websocket: WebSocket,
    conversation_id: str,
    tenant_id: str = Query(...),
    token: Optional[str] = Query(None),
):
    """Real-time conversation updates — messages, analysis results, lead score changes."""
    await manager.connect(conversation_id, websocket)
    try:
        # Send connection acknowledgment
        await manager.send_to(websocket, {
            "type": "connected",
            "conversation_id": conversation_id,
            "tenant_id": tenant_id,
        })

        while True:
            raw = await websocket.receive_json()
            msg_type = raw.get("type")

            if msg_type == "ping":
                await manager.send_to(websocket, {"type": "pong"})

            elif msg_type == "message":
                # Handle incoming message from client
                content = raw.get("content", "")
                interaction_id = raw.get("interaction_id")
                msg = _handle_incoming_message(conversation_id, tenant_id, content, interaction_id)
                await manager.broadcast(conversation_id, {
                    "type": "message",
                    "data": msg,
                })

            elif msg_type == "request_analysis":
                # Trigger analysis for an interaction
                interaction_id = raw.get("interaction_id")
                publisher.publish(
                    EVENT_INTERACTION_ANALYSIS_REQUESTED,
                    tenant_id,
                    {"interaction_id": interaction_id, "conversation_id": conversation_id},
                )
                await manager.send_to(websocket, {
                    "type": "analysis_requested",
                    "interaction_id": interaction_id,
                })

    except WebSocketDisconnect:
        logger.info(f"WS disconnected: conversation={conversation_id}")
    except Exception as e:
        logger.error(f"WS error for {conversation_id}: {e}")
    finally:
        manager.disconnect(conversation_id, websocket)


@router.websocket("/ws/voice/{conversation_id}")
async def voice_ws(
    websocket: WebSocket,
    conversation_id: str,
    tenant_id: str = Query(...),
    interaction_id: Optional[str] = Query(None),
    worker_type: Optional[str] = Query(None),
    lead_id: Optional[str] = Query(None),
    access_token: Optional[str] = Query(None),
):
    """Real-time voice streaming — receives audio/text chunks, streams analysis back.

    Modes:
    1. Client-side STT: browser sends transcribed text, server analyzes
    2. Audio upload: browser sends base64 WAV chunks, server Whisper STT + analyzes

    When *worker_type* (sdr / sales / support) is supplied, each turn's reply is
    produced by that AI Workforce worker via the orchestrator (with SDR->Sales
    auto-handoff on qualification) instead of the generic grounded chat answer,
    so "speak, and the right worker replies" works over the same socket.
    """
    await manager.connect(conversation_id, websocket)
    # Product clients authenticate with the same short-lived tenant JWT used
    # by HTTP APIs. The legacy /voice-test route remains tokenless local demo
    # tooling for backward compatibility.
    if access_token:
        try:
            from app.core.security import decode_access_token
            from app.database.session import SessionLocal
            from sqlalchemy import text as sa_text
            claims = decode_access_token(access_token)
            if str(claims.get("tenant_id")) != str(tenant_id):
                raise ValueError("Tenant claim mismatch")
            with SessionLocal() as auth_db:
                owner = auth_db.execute(
                    sa_text("SELECT tenant_id FROM conversations WHERE id = :id"),
                    {"id": conversation_id},
                ).scalar()
            if owner is None or str(owner) != str(tenant_id):
                raise ValueError("Conversation tenant mismatch")
        except Exception:
            await manager.send_to(websocket, {"type": "auth_error", "error": "Invalid or mismatched voice session"})
            await websocket.close(code=1008)
            manager.disconnect(conversation_id, websocket)
            return
    partial_transcript = []
    upload_audio_chunks: list[bytes] = []
    active_turn_task: asyncio.Task | None = None

    async def start_turn(transcript: str, audio=None, language: str | None = None) -> None:
        """Queue turns in order; never cut off an answer already being spoken.

        *audio* is the preprocessed float32 array of the utterance (when the turn
        came from real speech) so tone/prosody can drive the lead scores;
        *language* is the STT-detected language so the reply can match it.
        """
        nonlocal active_turn_task
        previous_turn = active_turn_task

        async def run_turn() -> None:
            if previous_turn and not previous_turn.done():
                try:
                    await previous_turn
                except asyncio.CancelledError:
                    return
            await _trigger_voice_analysis(
                conversation_id, tenant_id, interaction_id, transcript, websocket,
                worker_type=worker_type, lead_id=lead_id, audio=audio, language=language,
            )

        if previous_turn and not previous_turn.done():
            await manager.send_to(websocket, {"type": "voice_turn_queued", "conversation_id": conversation_id})
            logger.info("voice_turn_queued conversation={}", conversation_id)
        active_turn_task = asyncio.create_task(run_turn())

    try:
        await manager.send_to(websocket, {
            "type": "voice_connected",
            "conversation_id": conversation_id,
        })

        while True:
            raw = await websocket.receive_json()
            msg_type = raw.get("type")

            if msg_type == "transcript_chunk":
                text = raw.get("text", "")
                is_final = raw.get("is_final", False)
                typed_language = raw.get("language")
                partial_transcript.append(text)

                await manager.send_to(websocket, {
                    "type": "transcript_received",
                    "text": text,
                    "is_final": is_final,
                    "partial": " ".join(partial_transcript[-5:]),
                    "language": typed_language,
                })

                if is_final:
                    full_text = " ".join(partial_transcript)
                    partial_transcript.clear()
                    await start_turn(full_text, language=typed_language)

            elif msg_type == "upload_audio":
                upload_audio_chunks.clear()

            elif msg_type == "upload_audio_chunk":
                chunk = base64.b64decode(raw.get("data", ""))
                upload_audio_chunks.append(chunk)
                await manager.send_to(websocket, {
                    "type": "upload_audio_progress",
                    "bytes_received": sum(len(c) for c in upload_audio_chunks),
                })

            elif msg_type == "upload_audio_end":
                audio_bytes = b"".join(upload_audio_chunks)
                upload_audio_chunks.clear()
                if not audio_bytes:
                    await manager.send_to(websocket, {
                        "type": "upload_audio_error",
                        "error": "No audio data received",
                    })
                    continue

                await manager.send_to(websocket, {
                    "type": "upload_audio_received",
                    "bytes": len(audio_bytes),
                })

                # Debug: save raw audio before any processing
                from app.config.settings import get_settings
                _debug_settings = get_settings()
                if _debug_settings.DEBUG_SAVE_AUDIO:
                    _debug_dir = Path("debug_audio")
                    _debug_dir.mkdir(exist_ok=True)
                    _ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:23]
                    _debug_path = _debug_dir / f"utterance_{_ts}.wav"
                    _debug_path.write_bytes(audio_bytes)
                    logger.info("Saved raw audio to {}", _debug_path)

                # Transcribe with configured STT provider
                audio_np = None
                try:
                    from app.analysis.pipelines.speech.preprocessing import SpeechPreprocessor
                    from app.config.settings import get_settings
                    _stt_settings = get_settings()
                    preprocessor = SpeechPreprocessor(
                        target_sr=16000,
                        max_audio_seconds=_stt_settings.MAX_VOICE_AUDIO_SECONDS,
                        enable_noise_reduction=_stt_settings.ENABLE_NOISE_REDUCTION,
                        use_silero_vad=True,
                    )
                    audio_np, sr = preprocessor.preprocess(audio_bytes)

                    if _stt_settings.SPEECH_TO_TEXT_PROVIDER.lower() != "elevenlabs":
                        raise RuntimeError("Voice calls require SPEECH_TO_TEXT_PROVIDER=elevenlabs")
                    from app.analysis.services.elevenlabs_service import ElevenLabsService
                    stt_started = time.perf_counter()
                    result = await asyncio.to_thread(ElevenLabsService.transcribe, audio_np, sr)
                    transcript = result["text"]
                    # STT-detected spoken language, so the reply can match it.
                    detected_language = result.get("language") or result.get("language_code")
                    logger.info("voice_latency stage=stt duration_ms={:.0f} language={} conversation={}", (time.perf_counter() - stt_started) * 1000, detected_language, conversation_id)
                except Exception as exc:
                    logger.error(f"Transcription failed: {exc}")
                    transcript = ""
                    detected_language = None

                if not transcript:
                    transcript = "[Could not transcribe this audio]"

                partial_transcript.append(transcript)
                await manager.send_to(websocket, {
                    "type": "transcript_received",
                    "text": transcript,
                    "is_final": True,
                    "partial": transcript,
                    "language": detected_language,
                })
                # Pass the real audio (tone) and detected language into the turn.
                await start_turn(transcript, audio=audio_np, language=detected_language)

            elif msg_type == "voice_end":
                full_transcript = " ".join(partial_transcript)
                await manager.send_to(websocket, {
                    "type": "voice_ended",
                    "full_transcript": full_transcript,
                })
                partial_transcript.clear()

    except WebSocketDisconnect:
        logger.info(f"WS voice disconnected: conversation={conversation_id}")
    except Exception as e:
        logger.error(f"WS voice error: {e}")
    finally:
        manager.disconnect(conversation_id, websocket)


# ── Internal helpers ──────────────────────────────────────────────

def _handle_incoming_message(
    conversation_id: str,
    tenant_id: str,
    content: str,
    interaction_id: Optional[str] = None,
) -> dict:
    """Create a message event and return message data."""
    msg_id = str(uuid.uuid4())
    message_data = {
        "id": msg_id,
        "conversation_id": conversation_id,
        "interaction_id": interaction_id,
        "role": "user",
        "content": content,
        "created_at": datetime.utcnow().isoformat(),
    }

    publisher.publish(EVENT_MESSAGE_ADDED, tenant_id, message_data)
    return message_data


async def _trigger_voice_analysis(
    conversation_id: str,
    tenant_id: str,
    interaction_id: Optional[str],
    transcript: str,
    ws: WebSocket,
    worker_type: Optional[str] = None,
    lead_id: Optional[str] = None,
    audio=None,
    language: Optional[str] = None,
):
    """Run voice pipeline: filler, then a spoken reply, sentence by sentence.

    The reply comes from one of two sources:
      * If *worker_type* (sdr / sales / support) is set, run_worker() dispatches
        the turn to that AI Workforce worker (with SDR->Sales auto-handoff), and
        its reply is spoken. This is how a live voice call is handled by a
        specific worker rather than a generic assistant.
      * Otherwise, chat_pipeline() (app/services/rag/pipelines/chat.py) produces
        a grounded, cited answer -- the same path the Support worker and the
        proven /chat/ endpoint use.

    Neither path uses app/services/rag/service.py's RAGService.stream_answer():
    that class calls generate_answer()/generate_answer_streamed() with
    mode=/language=/max_tokens=/model_name= kwargs that
    app/services/rag/llm/generator.py's real generate_answer(question, context,
    system_prompt) does not accept, and generate_answer_streamed does not exist
    there at all -- RAGService targets a local multi-model streaming backend that
    was never implemented (no local model weights are provisioned here either),
    so it fails on the first call. The tradeoff versus that intended design is
    that a turn speaks after the full answer is generated, not token-by-token.
    """
    import time as _time
    _pipeline_start = _time.perf_counter()
    from app.analysis.pipelines.language_service import LanguageService
    normalized_language = LanguageService.normalize(language)
    # BANT/MEDDIC shares the CPU models with RAG.  Start it only after the
    # answer has been spoken so it can never increase call-answer latency.
    def start_background_bant() -> None:
        analysis_task = asyncio.create_task(
            _run_analysis_and_notify(transcript, conversation_id, tenant_id, ws, audio=audio)
        )

        def _log_background_analysis(task: asyncio.Task) -> None:
            if task.cancelled():
                logger.warning("voice_background_bant status=cancelled conversation={}", conversation_id)
            elif task.exception():
                logger.error("voice_background_bant status=failed conversation={} error={}", conversation_id, task.exception())

        analysis_task.add_done_callback(_log_background_analysis)

    # Step 0: Quick-assistant gate -- skip RAG entirely for simple patterns.
    # Deliberately bypassed when a worker is driving the call: the quick
    # assistant's canned sales/greeting replies would otherwise preempt exactly
    # the buying-signal utterances (budget/demo/"ready to buy") an SDR or Sales
    # worker most needs to handle, silently swallowing the worker turn.
    if not worker_type and normalized_language == "en":
        from app.analysis.services.quick_assistant_service import QuickAssistantService
        quick_answer = QuickAssistantService.maybe_answer(transcript)
        if quick_answer is not None:
            logger.info("stage=quick_assistant_hit duration_ms={:.0f}", (_time.perf_counter() - _pipeline_start) * 1000)
            await _speak_answer(quick_answer, conversation_id, ws, language=normalized_language)
            start_background_bant()
            await manager.send_to(ws, {
                "type": "analysis_triggered",
                "conversation_id": conversation_id,
                "transcript_length": len(transcript),
            })
            return

    # 1. Generate filler immediately so the caller hears something right away
    t1 = _time.perf_counter()
    # The filler generator is currently English-only. Avoid mixing an English
    # filler into a turn whose STT language is non-English.
    filler = await generate_filler(transcript) if normalized_language == "en" else ""
    logger.info("stage=filler duration_ms={:.0f} text={}", (_time.perf_counter() - t1) * 1000, filler)
    if filler:
        await manager.send_to(ws, {
            "type": "filler",
            "text": filler,
            "conversation_id": conversation_id,
        })
        await _speak_single_sentence(
            filler, conversation_id, ws, -1, False,
            source="filler", pipeline_start=_pipeline_start, language=normalized_language,
        )

    # 2. Produce the reply — via a dispatched worker if one was requested,
    #    otherwise the generic grounded chat answer — then speak it.
    t2 = _time.perf_counter()
    if worker_type:
        from app.services.agents.orchestrator import run_worker, DISPATCHABLE_WORKER_TYPES
        from app.database.session import SessionLocal
        normalized_worker = worker_type.strip().lower()
        if normalized_worker in DISPATCHABLE_WORKER_TYPES:
            worker_db = SessionLocal()
            try:
                worker_result = await run_worker(
                    worker_db, worker_type=normalized_worker, tenant_id=tenant_id,
                    text=transcript, lead_id=lead_id, session_id=conversation_id, channel="voice",
                    response_language=normalized_language,
                )
                full_answer = worker_result.get("reply") or "I'm sorry, I don't have an answer for that right now."
                logger.info(
                    "stage=worker_reply worker={} duration_ms={:.0f} intent={} actions={}",
                    worker_result.get("worker"), (_time.perf_counter() - t2) * 1000,
                    worker_result.get("intent"), worker_result.get("actions"),
                )
                await manager.send_to(ws, {
                    "type": "worker_result",
                    "conversation_id": conversation_id,
                    "data": {k: v for k, v in worker_result.items() if k not in ("sdr_result",)},
                })
                await _speak_answer(full_answer, conversation_id, ws, language=normalized_language)
                start_background_bant()
                await manager.send_to(ws, {
                    "type": "analysis_triggered",
                    "conversation_id": conversation_id,
                    "transcript_length": len(transcript),
                })
                logger.info("stage=voice_pipeline_total duration_ms={:.0f}", (_time.perf_counter() - _pipeline_start) * 1000)
                return
            except Exception as exc:
                logger.error("stage=worker_dispatch_error worker={} error={}", normalized_worker, exc)
                # Fall through to the generic grounded answer below.
            finally:
                worker_db.close()
        else:
            logger.warning("Ignoring unknown voice worker_type={}; using grounded answer", worker_type)

    # 2b. Generic grounded answer (no worker requested, or worker dispatch failed).
    from app.services.rag.pipelines.chat import chat_pipeline
    result = await chat_pipeline(
        question=transcript, tenant_id=tenant_id, session_id=conversation_id,
        response_language=normalized_language,
    )
    full_answer = result.get("answer") or "I'm sorry, I don't have an answer for that right now."
    logger.info(
        "stage=chat_pipeline_complete duration_ms={:.0f} confidence={} supported={}",
        (_time.perf_counter() - t2) * 1000, result.get("confidence"), result.get("supported"),
    )
    await _speak_answer(full_answer, conversation_id, ws, language=normalized_language)

    logger.info("voice_latency stage=rag_retrieval elapsed_ms={:.0f} conversation={}", (_time.perf_counter() - _pipeline_start) * 1000, conversation_id)

    # Start BANT only after all answer audio has been delivered. This background
    # task (_run_analysis_and_notify) is the sole place that both computes and
    # persists lead_score/BANT/MEDDIC for this turn — see its docstring for why
    # this path does not also route through app/analysis/workers/analysis_worker.py.
    start_background_bant()

    await manager.send_to(ws, {
        "type": "analysis_triggered",
        "conversation_id": conversation_id,
        "transcript_length": len(transcript),
    })

    pipeline_total = (_time.perf_counter() - _pipeline_start) * 1000
    logger.info("stage=voice_pipeline_total duration_ms={:.0f}", pipeline_total)


async def _speak_single_sentence(
    text: str,
    conversation_id: str,
    ws: WebSocket,
    index: int,
    is_last: bool,
    source: str = "answer",
    pipeline_start: float | None = None,
    language: str | None = None,
):
    """TTS a single sentence and send audio via WebSocket."""
    text = _SPOKEN_SOURCE_RE.sub("", text).strip()
    if not text:
        return
    import time as _time
    _diag_t0 = _time.perf_counter()
    logger.debug("DIAG:tts_start idx={} chars={}", index, len(text))
    from app.analysis.services.elevenlabs_service import ElevenLabsService
    from app.config.settings import get_settings
    from app.analysis.pipelines.language_service import LanguageService
    settings = get_settings()
    t0 = _time.perf_counter()
    ts_path: Path | None = None
    try:
        ts_path = Path(settings.TTS_OUTPUT_DIR) / f"reply_{conversation_id}_{uuid.uuid4().hex[:8]}.mp3"
        spoken_language = LanguageService.normalize(language or LanguageService.detect(text))
        voice_id = settings.ELEVENLABS_TAMIL_VOICE_ID if spoken_language == "ta" else None
        await asyncio.to_thread(
            ElevenLabsService.synthesize,
            text=text,
            destination=ts_path,
            language=spoken_language,
            voice_id=voice_id,
        )
        audio_b64 = base64.b64encode(ts_path.read_bytes()).decode()
        await manager.send_to(ws, {
            "type": "tts_chunk",
            "conversation_id": conversation_id,
            "text": text,
            "audio_base64": audio_b64,
            "format": "mp3",
            "index": index,
            "is_last": is_last,
            "source": source,
        })
        elapsed_ms = (_time.perf_counter() - t0) * 1000
        logger.info("stage=tts_sentence source={} idx={} chars={} duration_ms={:.0f}", source, index, len(text), elapsed_ms)
        if pipeline_start is not None and (source == "filler" or index == 0):
            stage = "filler_tts" if source == "filler" else "first_answer_tts"
            logger.info("voice_latency stage={} elapsed_ms={:.0f} conversation={}", stage, (_time.perf_counter() - pipeline_start) * 1000, conversation_id)
    except Exception as exc:
        logger.error("stage=tts_sentence_error idx={} error={}", index, exc)
    finally:
        # TTS chunks are transported immediately over the socket; retaining a
        # file per sentence would grow the local disk without adding evidence.
        if ts_path is not None:
            try:
                ts_path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("stage=tts_cleanup_error path={} error={}", ts_path, exc)


async def _speak_answer(
    text: str, conversation_id: str, ws: WebSocket,
    max_sentence_len: int = 400, language: str | None = None,
):
    """Split *text* into sentences and TTS each one, sending audio to client incrementally."""
    import time as _time
    import re as _re

    # Simple sentence splitter: ., !, ?, newline, or clause break after max_sentence_len
    sentence_end = _re.compile(r"(?<=[.!?])\s+|(?<=\n)\s*")
    # Fallback: split on mid-sentence clause breaks if a sentence is too long
    clause_break = _re.compile(r"(?<=[,;:])\s+")

    def _chunk_sentences(full: str):
        """Yield sentences, splitting long ones on clause boundaries."""
        for part in sentence_end.split(full):
            part = part.strip()
            if not part:
                continue
            if len(part) <= max_sentence_len:
                yield part
            else:
                # Split on clause breaks
                clauses = clause_break.split(part)
                buf = ""
                for clause in clauses:
                    if len(buf) + len(clause) + 1 <= max_sentence_len:
                        buf = (buf + " " + clause).strip()
                    else:
                        if buf:
                            yield buf
                        buf = clause
                if buf:
                    yield buf

    sentences = list(_chunk_sentences(text))
    logger.info("stage=tts_sentences count={} total_chars={}", len(sentences), len(text))
    for i, sentence in enumerate(sentences):
        await _speak_single_sentence(
            sentence, conversation_id, ws, i, i == len(sentences) - 1,
            language=language,
        )


async def _run_analysis_and_notify(
    transcript: str,
    conversation_id: str,
    tenant_id: str,
    ws: WebSocket,
    audio=None,
):
    """Run BANT/MEDDIC analysis in background; send WS update, then persist + publish.

    This is the only place a voice turn's lead_scores/BANT get computed, so it's
    also the only place they get saved. Deliberately does NOT go through
    app/analysis/workers/analysis_worker.py's EVENT_CONVERSATION_ANALYSIS_REQUESTED
    path: that worker's own ConversationAnalysisPipeline would redundantly
    re-derive sentiment/emotion from the transcript with a *different*,
    BANT-less scorer (app/analysis/lead_scoring/scorer.py) and race this
    function to overwrite the same ConversationAnalysis row. Persisting the
    result already computed here and publishing EVENT_CONVERSATION_ANALYSIS_COMPLETED
    directly keeps one shape, one write, one source of truth — and still lets
    app/workers/lead_scoring_worker.py (or anything else) react to completion.
    """
    try:
        from app.analysis.services.voice_analysis_pipeline import VoiceAnalysisPipeline
        VoiceAnalysisPipeline.initialize()
        logger.info("=== VOICE_TRACE analysis_start audio={}", "yes" if audio is not None else "no")
        # Pass real audio so VoiceEmotionService and fusion run on the caller's
        # tone. Relationship/composite confidence can use that signal while
        # the other business metrics remain transcript/evidence based.
        analysis_result = await VoiceAnalysisPipeline.analyze(
            text=transcript,
            audio=audio,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
        )
        logger.info("=== VOICE_TRACE analysis_complete raw={}", analysis_result)
        await manager.send_to(ws, {
            "type": "voice_analysis",
            "conversation_id": conversation_id,
            "data": analysis_result,
        })
    except Exception as e:
        logger.error("=== VOICE_TRACE analysis_exception: {}", e)
        return

    try:
        lead_scores = analysis_result.get("lead_scores") or {}
        bant = analysis_result.get("bant") or {}
        combined_lead_score = {**lead_scores, "bant": bant}

        from app.analysis.services.conversation_analysis_service import ConversationAnalysisService
        analysis_service = ConversationAnalysisService()
        await asyncio.to_thread(analysis_service.create_analysis, conversation_id=conversation_id, tenant_id=tenant_id)
        saved = await asyncio.to_thread(
            analysis_service.update_complete_analysis,
            conversation_id=conversation_id,
            analysis={
                "transcript": {"full_text": transcript, "segments": [{"text": transcript, "speaker": "user"}]},
                "sentiment": analysis_result.get("sentiment") or {},
                # VoiceAnalysisPipeline.analyze() is called with text only (no
                # audio array), so voice_emotion is never populated here; pass
                # None rather than {} so AnalysisOutputValidator.validate_all()
                # skips it instead of failing the whole write on "emotion data
                # is empty" for a field that was never meant to be present.
                "emotion": analysis_result.get("voice_emotion") or None,
                "fusion": analysis_result.get("fusion") or {},
                "lead_score": combined_lead_score,
            },
        )
        if saved:
            publisher.publish(EVENT_CONVERSATION_ANALYSIS_COMPLETED, tenant_id, {
                "conversation_id": conversation_id,
                "status": "completed",
                "lead_score": combined_lead_score,
                "source": "voice",
            })
    except Exception as e:
        logger.error("=== VOICE_TRACE analysis_persist_exception: {}", e)


def _build_reply_text(transcript: str, analysis: dict | None = None) -> str:
    """Build a brief reply based on the analysis results."""
    if analysis and analysis.get("lead_scores"):
        intent = analysis["lead_scores"].get("intent", "")
        sentiment = analysis.get("sentiment", {})
        label = sentiment.get("sentiment", "neutral")
        if label in ("positive", "very positive"):
            return f"I'm glad to hear that. Let me make a note of your interest. {intent}"
        elif label in ("negative", "very negative"):
            return f"I understand your concern. Let me escalate this to the right team. {intent}"
    return "Thank you. I've noted what you said and I'll process that information."


def _bytes_to_np_float32(data: bytes) -> np.ndarray:
    """Convert raw WAV bytes to float32 numpy array."""
    import io as _io
    import wave as _wave
    with _wave.open(_io.BytesIO(data), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    return samples
