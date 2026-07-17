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
):
    """Real-time voice streaming — receives audio/text chunks, streams analysis back.

    Modes:
    1. Client-side STT: browser sends transcribed text, server analyzes
    2. Audio upload: browser sends base64 WAV chunks, server Whisper STT + analyzes
    """
    await manager.connect(conversation_id, websocket)
    partial_transcript = []
    upload_audio_chunks: list[bytes] = []
    active_turn_task: asyncio.Task | None = None

    async def start_turn(transcript: str) -> None:
        """Queue turns in order; never cut off an answer already being spoken."""
        nonlocal active_turn_task
        previous_turn = active_turn_task

        async def run_turn() -> None:
            if previous_turn and not previous_turn.done():
                try:
                    await previous_turn
                except asyncio.CancelledError:
                    return
            await _trigger_voice_analysis(conversation_id, tenant_id, interaction_id, transcript, websocket)

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
                partial_transcript.append(text)

                await manager.send_to(websocket, {
                    "type": "transcript_received",
                    "text": text,
                    "is_final": is_final,
                    "partial": " ".join(partial_transcript[-5:]),
                })

                if is_final:
                    full_text = " ".join(partial_transcript)
                    partial_transcript.clear()
                    await start_turn(full_text)

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
                    logger.info("voice_latency stage=stt duration_ms={:.0f} conversation={}", (time.perf_counter() - stt_started) * 1000, conversation_id)
                except Exception as exc:
                    logger.error(f"Transcription failed: {exc}")
                    transcript = ""

                if not transcript:
                    transcript = "[Could not transcribe this audio]"

                partial_transcript.append(transcript)
                await manager.send_to(websocket, {
                    "type": "transcript_received",
                    "text": transcript,
                    "is_final": True,
                    "partial": transcript,
                })
                await start_turn(transcript)

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
):
    """Run voice pipeline: RAG streaming ‖ filler → incremental TTS → Kafka event.

    RAG answer generation is streamed token-by-token; completed sentences
    are TTS'd immediately without waiting for the full answer.
    """
    import time as _time
    _pipeline_start = _time.perf_counter()
    # BANT/MEDDIC shares the CPU models with RAG.  Start it only after the
    # answer has been spoken so it can never increase call-answer latency.
    def start_background_bant() -> None:
        analysis_task = asyncio.create_task(
            _run_analysis_and_notify(transcript, conversation_id, tenant_id, ws)
        )

        def _log_background_analysis(task: asyncio.Task) -> None:
            if task.cancelled():
                logger.warning("voice_background_bant status=cancelled conversation={}", conversation_id)
            elif task.exception():
                logger.error("voice_background_bant status=failed conversation={} error={}", conversation_id, task.exception())

        analysis_task.add_done_callback(_log_background_analysis)
    from app.services.rag.service import get_rag_service

    # Step 0: Quick-assistant gate — skip RAG entirely for simple patterns
    from app.analysis.services.quick_assistant_service import QuickAssistantService
    quick_answer = QuickAssistantService.maybe_answer(transcript)
    if quick_answer is not None:
        logger.info("stage=quick_assistant_hit duration_ms={:.0f}", (_time.perf_counter() - _pipeline_start) * 1000)
        await _speak_answer(quick_answer, conversation_id, ws)
        return

    rag_service = get_rag_service()
    stream_meta: dict = {}

    # 0a. Start RAG answer streaming (runs pipeline eagerly in bg, tokens queued)
    rag_gen = rag_service.stream_answer(
        question=transcript, tenant_id=tenant_id, meta=stream_meta, response_style="tamil",
    )
    token_queue: asyncio.Queue = asyncio.Queue()
    first_token_logged = False

    async def _fill_token_queue():
        nonlocal first_token_logged
        try:
            async for token in rag_gen:
                if not first_token_logged:
                    first_token_logged = True
                    logger.info("voice_latency stage=rag_first_token elapsed_ms={:.0f} conversation={}", (_time.perf_counter() - _pipeline_start) * 1000, conversation_id)
                logger.debug("DIAG:token_received seq={} token={!r:.40}", token_queue.qsize(), token)
                token_queue.put_nowait(token)
        except Exception as exc:
            logger.error("stage=rag_stream_producer error={}", exc)
        finally:
            logger.debug("DIAG:token_sentinel token_queue.qsize={}", token_queue.qsize())
            token_queue.put_nowait(None)

    producer_task = asyncio.create_task(_fill_token_queue())

    # 1. Generate filler concurrently
    t1 = _time.perf_counter()
    filler = await generate_filler(transcript)
    logger.info("stage=filler duration_ms={:.0f} text={}", (_time.perf_counter() - t1) * 1000, filler)
    if filler:
        await manager.send_to(ws, {
            "type": "filler",
            "text": filler,
            "conversation_id": conversation_id,
        })
        await _speak_single_sentence(
            filler, conversation_id, ws, -1, False,
            source="filler", pipeline_start=_pipeline_start,
        )
    # 2. Consume token stream; buffer into sentences and TTS as each completes
    t2 = _time.perf_counter()
    sentence_buf = ""
    sentence_idx = 0
    full_answer = ""

    logger.debug("DIAG:consumer_start t2={:.6f}", t2)
    while True:
        token = await token_queue.get()
        if token is None:
            logger.debug("DIAG:consumer_sentinel_received")
            break
        logger.debug("DIAG:consumer_token_received buf_len={} token={!r:.40}", len(sentence_buf), token)
        full_answer += token
        sentence_buf += token
        while True:
            # Split on punctuation (ASCII . ! ? and Indic danda)
            m = re.search(r"(?<=[.!?\u0964\u0965])\s+", sentence_buf)
            if m is None and len(sentence_buf) >= 200:
                # Safety net: flush long buffer even without punctuation
                last_ws = sentence_buf.rfind(" ")
                if last_ws > 0:
                    sentence = sentence_buf[:last_ws].strip()
                    sentence_buf = sentence_buf[last_ws:].strip()
                else:
                    sentence = sentence_buf[:200].strip()
                    sentence_buf = sentence_buf[200:].strip()
                if sentence:
                    logger.debug("DIAG:sentence_boundary idx={} chars={} sentence={!r:.60}", sentence_idx, len(sentence), sentence)
                    await _speak_single_sentence(sentence, conversation_id, ws, sentence_idx, False)
                    sentence_idx += 1
                    continue
                break
            if m is None:
                break
            sentence = sentence_buf[:m.end()].strip()
            sentence_buf = sentence_buf[m.end():]
            if sentence:
                logger.debug("DIAG:sentence_boundary idx={} chars={} sentence={!r:.60}", sentence_idx, len(sentence), sentence)
                await _speak_single_sentence(sentence, conversation_id, ws, sentence_idx, False)
                sentence_idx += 1

    # Flush remaining partial sentence
    if sentence_buf.strip():
        await _speak_single_sentence(sentence_buf.strip(), conversation_id, ws, sentence_idx, True)

    # 3. Log timing from stream_meta
    stage_timings = stream_meta.get("stage_timings_ms", {})
    rag_total_ms = stream_meta.get("latency_ms", "?")
    logger.info(
        "stage=rag_stream_complete duration_ms={:.0f} classify={} embed={} search={} context={} gen={} total={}",
        (_time.perf_counter() - t2) * 1000,
        stage_timings.get("classify_ms", "?"),
        stage_timings.get("embed_query_ms", "?"),
        stage_timings.get("qdrant_search_ms", "?"),
        stage_timings.get("context_build_ms", "?"),
        stage_timings.get("generation_ms", "?"),
        rag_total_ms,
    )

    logger.info("voice_latency stage=rag_retrieval elapsed_ms={:.0f} search_ms={} embed_ms={} conversation={}", (_time.perf_counter() - _pipeline_start) * 1000, stage_timings.get("qdrant_search_ms", "?"), stage_timings.get("embed_query_ms", "?"), conversation_id)

    # Start BANT only after all answer audio has been delivered.
    start_background_bant()

    # 4. Publish domain event for downstream RAG persistence (fire-and-forget)
    t3 = _time.perf_counter()
    analysis_data = {
        "conversation_id": conversation_id,
        "interaction_id": interaction_id or "",
        "transcript": transcript,
        "answer": full_answer,
        "source": "voice",
    }
    publisher.publish(EVENT_INTERACTION_ANALYSIS_REQUESTED, tenant_id, analysis_data)
    logger.info("stage=kafka_publish duration_ms={:.0f}", (_time.perf_counter() - t3) * 1000)

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
    try:
        ts_path = Path(settings.TTS_OUTPUT_DIR) / f"reply_{conversation_id}_{uuid.uuid4().hex[:8]}.mp3"
        language = LanguageService.detect(text)
        voice_id = settings.ELEVENLABS_TAMIL_VOICE_ID if language == "ta" else None
        await asyncio.to_thread(
            ElevenLabsService.synthesize,
            text=text,
            destination=ts_path,
            language=language,
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


async def _speak_answer(text: str, conversation_id: str, ws: WebSocket, max_sentence_len: int = 400):
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
        await _speak_single_sentence(sentence, conversation_id, ws, i, i == len(sentences) - 1)


async def _run_analysis_and_notify(
    transcript: str,
    conversation_id: str,
    tenant_id: str,
    ws: WebSocket,
):
    """Run BANT/MEDDIC analysis in background; send WS update when done."""
    try:
        from app.analysis.services.voice_analysis_pipeline import VoiceAnalysisPipeline
        VoiceAnalysisPipeline.initialize()
        logger.info("=== VOICE_TRACE analysis_start")
        analysis_result = await VoiceAnalysisPipeline.analyze(
            text=transcript,
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
