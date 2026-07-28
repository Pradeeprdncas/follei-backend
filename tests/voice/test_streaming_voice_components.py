import asyncio

from app.analysis.services.streaming_tts_service import PhraseBuffer
from app.analysis.services.tanglish_style import prompt_instruction, vocabulary_for
from app.api.websocket_handler import _strip_markdown_for_speech
from app.services.rag.filler_service import generate_filler
from app.services.rag.llm import generator


def test_phrase_buffer_emits_punctuation_boundary_and_flushes_tail():
    buffer = PhraseBuffer(min_chars=12, max_chars=40)
    assert buffer.push("This is a complete sentence. ") == ["This is a complete sentence."]
    assert buffer.push("Short tail") == []
    assert buffer.flush() == "Short tail"


def test_phrase_buffer_caps_unpunctuated_text():
    buffer = PhraseBuffer(min_chars=10, max_chars=20)
    emitted = buffer.push("one two three four five six")
    assert emitted
    assert all(len(item) <= 20 for item in emitted)


def test_filler_matches_spoken_language():
    assert "pricing" in asyncio.run(generate_filler("Can you check pricing?", "en")).lower()
    assert "budget" in asyncio.run(generate_filler("என்னோட budget 10K", "ta")).lower()
    assert "ठीक" in asyncio.run(generate_filler("कीमत क्या है?", "hi"))


def test_filler_varies_without_losing_context():
    first = asyncio.run(generate_filler("My budget is 10K", "ta", conversation_id="conv-1"))
    second = asyncio.run(generate_filler("My budget is 10K", "ta", conversation_id="conv-1"))
    assert first != second
    assert "budget" in first.lower()
    assert "budget" in second.lower()


def test_tanglish_prompt_uses_topic_vocabulary_from_reference_list():
    words = vocabulary_for("I am the owner and my budget is 10K for this sales platform")
    assert {"budget", "sales", "owner", "platform"}.issubset(set(words))
    instruction = prompt_instruction("Need pricing in one week")
    assert "day-to-day Tanglish" in instruction
    assert "Markdown" in instruction


def test_markdown_is_removed_before_speech():
    spoken = _strip_markdown_for_speech("**Follei**\n- Fast sales\n- `24/7` support")
    assert "*" not in spoken
    assert "`" not in spoken
    assert "Follei" in spoken
    assert "24/7" in spoken


def test_generator_streams_tokens_to_callback(monkeypatch):
    async def fake_stream(_messages, **_kwargs):
        for token in ("Tailored ", "answer."):
            yield token

    monkeypatch.setattr(generator, "stream", fake_stream)
    received = []

    async def collect(token):
        received.append(token)

    answer = asyncio.run(
        generator.generate_answer(
            "Question",
            "Lead context",
            "Be helpful",
            on_token=collect,
        )
    )
    assert answer == "Tailored answer."
    assert received == ["Tailored ", "answer."]
