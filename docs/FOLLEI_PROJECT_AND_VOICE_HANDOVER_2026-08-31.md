# Follei Project and Voice AI Handover

Status date: 2026-08-31
Branch: `codex/voice-training-handover`
Repository: `/Users/SkyneTBee/dev/follei-backend`
Purpose: verification handover of the current platform, voice runtime, training plan, accent/prosody adaptation, and consented voice cloning

## 1. Executive Summary

Follei is a multi-tenant autonomous business-workforce platform. It ingests a client's business data, retrieves tenant-scoped knowledge, maintains lead/customer state, routes work to specialized business workers, generates grounded responses, and can deliver those responses through a real-time voice conversation path.

The current repository contains two different levels of voice capability:

1. **Implemented runtime:** WebSocket voice calls, ElevenLabs STT, grounded/worker response generation, Tanglish output guidance, phrase buffering, TTS provider selection, audio chunk delivery, latency events, and barge-in handling.
2. **Prepared but not trained:** an IndicF5 benchmark, consent/provenance manifests, dataset validation, F5-compatible dataset export, controlled audio ingestion, and an IndicF5 model-server adapter.

No custom Follei Tamil model has been trained yet. No YouTuber voice has been cloned. The current default TTS setting still selects the existing ElevenLabs/gTTS path unless deployment configuration switches to the Follei model server.

The target is not guaranteed "perfect Tamil" from one training run. The engineering target is native-quality conversational Tamil/Tanglish measured by held-out prompts and fluent Tamil listeners. A model is promoted only after it passes pronunciation, prosody, entity, latency, concurrency, and consent gates.

## 2. Current Git and Verification State

The repository is on `main...origin/main` with many modified and untracked files. These include broader onboarding, ingestion, RAG, frontend, and voice work. The worktree must not be cleaned or reset without first separating and preserving the owner's changes.

Voice-related changes currently present include:

- `app/analysis/services/streaming_tts_service.py`
- `app/analysis/services/speech_text_normalizer.py`
- `app/api/tts/router.py`
- `app/api/websocket_handler.py`
- `app/config/settings.py`
- `app/services/tts/tts_service.py`
- `tests/voice/test_streaming_voice_components.py`
- `voice_training/`
- `docs/FOLLEI_VOICE_AI_TRAINING_AND_RUNTIME_SPEC.md`

Verification completed during this work:

- Modified Python voice modules compile.
- `git diff --check` passes.
- Speech normalizer smoke test passes.
- Dataset validator smoke test passes with train/validation/test clips.
- F5 CSV export smoke test produces the required `audio_file|text` format.

The full test suite was not rerun in the active shell because `pytest` is not installed there. The existing `docs/HANDOVER.md` reports an older successful baseline dated 2026-08-10; that record must not be treated as verification of the uncommitted 2026-08-31 voice changes.

## 3. Platform Architecture Today

### 3.1 Application tier

The backend is a FastAPI application created in `app/main.py`. It exposes authentication, onboarding, ingestion, knowledge, lead/customer, integration, campaign, conversation, analytics, TTS, and WebSocket surfaces.

The lightweight runtime consists primarily of:

| Process | Responsibility |
|---|---|
| API | HTTP APIs, OAuth callbacks, onboarding, queries, conversations, and WebSockets |
| Indexing worker | Parse, classify, chunk, embed, and index documents |
| Knowledge-sync worker | Project durable PostgreSQL/outbox state into retrieval stores |
| Google Workspace worker | Synchronize Gmail, Drive, Contacts, and Calendar |
| Website-ingestion worker | Crawl approved websites and fan out indexing jobs |

The optional full profile adds conversation analysis, lead scoring, mail automation, flows, and CRM synchronization.

### 3.2 Data and infrastructure tier

| System | Current role |
|---|---|
| PostgreSQL | Tenant, user, lead, customer, conversation, job, source, onboarding, and durable workflow state |
| Redis | Caching, deduplication, real-time coordination, and short-lived state |
| Kafka | Durable ingestion, analysis, and domain-event work queues |
| MinIO/object storage | Original documents, attachments, and generated artifacts where configured |
| FerretDB/DocumentDB | Chunk text and flexible structural metadata in the standard profile |
| Qdrant | Tenant-filtered vector and hybrid retrieval |

### 3.3 Knowledge ingestion and retrieval

```text
Client website/files/Google Workspace/CRM
  -> source registration and permissions
  -> parser and document classification
  -> structure-aware chunks
  -> embeddings
  -> PostgreSQL/FerretDB/Qdrant
  -> tenant-filtered retrieval
  -> grounded response generation
```

Knowledge must always be filtered by `tenant_id`. Client A's chunks, cache entries, summaries, leads, and responses must never appear in Client B's request.

### 3.4 Business worker architecture

`app/services/agents/orchestrator.py` routes requests to specialized worker types such as:

- SDR
- Sales
- Support
- Customer success
- Collections
- Account manager
- Executive/general

The worker or grounded RAG path receives tenant knowledge, conversation state, and lead/customer context. Its response is generated as text first. TTS is a delivery service and must never invent business facts.

## 4. Current Voice Architecture

### 4.1 Implemented call path

```text
Caller/browser audio
  -> /ws/voice/{conversation_id}
  -> audio preprocessing and VAD
  -> ElevenLabs speech-to-text
  -> normalized language
  -> selected business worker or grounded RAG chat
  -> streaming generation tokens
  -> Tanglish style policy
  -> phrase buffer
  -> TTS provider
  -> Base64 audio chunks over WebSocket
  -> caller/browser playback
```

Important current details:

- Voice-call STT currently requires `SPEECH_TO_TEXT_PROVIDER=elevenlabs`.
- Tamil is detected reliably when Tamil Unicode is present.
- Romanized Tamil needs an explicit `language: "ta"` override because Latin-only Tamil can otherwise look like English.
- The Tanglish prompt asks for Tamil grammar in Tamil script while retaining familiar English words in Latin script.
- Markdown is stripped before speech synthesis.
- LLM tokens are buffered into phrases to avoid waiting for the full answer.
- A caller interruption cancels the active response turn.
- Stage latency events are sent to the client.

### 4.2 TTS providers

The runtime has one stable provider interface and two provider implementations:

1. `ConfiguredTTSProvider`: existing ElevenLabs path with gTTS fallback.
2. `FolleiModelTTSProvider`: calls a dedicated Tamil model server at `/synthesize`.

Current default configuration:

```text
TTS_PROVIDER=elevenlabs
TTS_SKIP_ELEVENLABS=true
```

This means development can fall back to gTTS, which explains flat, robotic, or inaccurate Tamil delivery. The custom model will not be used until a GPU model server is running and `TTS_PROVIDER=follei` is configured.

### 4.3 Internal TTS request

```json
{
  "text": "உங்க account-ல இன்னும் payment வரல சார்.",
  "language": "ta",
  "model": "tamil-prosody-v1",
  "accent": "spoken-tamil",
  "prosody_profile": "conversational",
  "voice_profile": null,
  "speed": 1.0
}
```

Meaning:

| Field | Responsibility |
|---|---|
| `text` | Final speakable Tamil/Tanglish text |
| `language` | Language frontend and pronunciation routing |
| `model` | Versioned Tamil acoustic/prosody checkpoint |
| `accent` | Approved accent preset, separate from speaker identity |
| `prosody_profile` | Conversational, support, sales, empathy, or other tested delivery style |
| `voice_profile` | Owned/licensed voice identity; null during neutral baseline evaluation |
| `speed` | Speaking-rate control |

The current zero-shot model server deliberately rejects named `voice_profile` values. A named identity is enabled only after consented voice-adaptation work exists.

## 5. How the Four AI Model Roles Work Together

Follei should be understood as four model roles, not one giant model.

### Model 1: streaming STT

Purpose:

- Convert caller audio into partial and final transcripts.
- Detect Tamil, English, or another supported language.
- Supply confidence and timing information.

It does not retrieve client data or decide what to say.

### Model 2: conversation controller

Purpose:

- Detect intent and objection.
- Update lead stage and sentiment.
- Decide whether RAG is required.
- Select the business worker and next-best action.
- Control turn-taking and response strategy.

Example structured result:

```json
{
  "intent": "payment_status",
  "lead_stage": "qualified",
  "sentiment": "concerned",
  "objection": null,
  "needs_retrieval": true,
  "next_best_action": "explain_status_and_offer_follow_up",
  "response_language": "ta"
}
```

This can begin as deterministic code plus small classifiers. It should not require the largest model in the system.

### Model 3: grounded generation model

Purpose:

- Read the controller decision.
- Retrieve only the current tenant's approved data.
- Use recent conversation and durable lead/customer state.
- Generate a short, grounded, lead-nurturing response.
- Return natural spoken Tanglish without Markdown.

Example:

```text
ஆமா சார், annual plan-க்கு three months EMI option இருக்கு.
உங்களுக்கு அந்த option-ோட full details சொல்லட்டுமா?
```

### Model 4: Tamil TTS

Purpose:

- Pronounce Tamil and code-mixed English correctly.
- Produce natural rhythm, pauses, emphasis, and sentence melody.
- Apply a tested prosody preset.
- Render an owned/licensed speaker identity when requested.

It receives final text. It does not access Qdrant, decide lead strategy, or alter factual content.

## 6. How Accent and Prosody Are Learned

Accent is not one switch and cannot be cleanly extracted from a person with a single algorithm. It is a combination of:

- Tamil phoneme realization
- Colloquial contractions
- Vowel and consonant timing
- Stress and emphasis
- Phrase rhythm
- Pause placement
- Pitch movement
- Code-switch behavior
- Speaking rate and energy

The foundation model supplies broad Tamil speech knowledge. Conversational adaptation data teaches the desired spoken-Tamil patterns. A reference clip or speaker adaptation supplies voice identity and some delivery characteristics.

The planned separation is:

```text
Tamil foundation and broad consented corpus
  -> pronunciation, phonology, colloquial rhythm, code switching

Owned/licensed style corpus
  -> conversational energy, pause patterns, emphasis categories

Owned deployment-speaker recordings
  -> timbre, pitch range, vocal texture, stable identity
```

A YouTuber's recordings contain both style and identity. Training directly on them does not reliably copy "accent only"; it can reproduce recognizable identity cues. Their material may be used only with explicit written permission covering AI training, commercial synthesis, and voice cloning where applicable.

"Speak perfect Tamil" is therefore an evaluation goal, not a promised training property. It is verified with held-out prompts and multiple fluent Tamil listeners.

## 7. Complete Training Process

### Phase 0: rights and objective

Before downloading or recording:

1. Define whether the source teaches Tamil/prosody, speaker identity, or both.
2. Obtain written permission/license for training and commercial deployment.
3. Record source ID, speaker ID, rights basis, scope, and withdrawal terms.
4. Select an owned deployment voice.

No source enters training unless `rights_confirmed=true`.

### Phase 1: clean baseline reference

Record an owned or consented 10-30 second reference clip with an exact transcript. Use it to benchmark zero-shot IndicF5 before training anything.

Generate the fixed evaluation set in `voice_training/eval/prompts.jsonl`, covering:

- Support and payment explanations
- Sales questions
- OTP and phone numbers
- Currency and percentages
- Dates and time
- Empathy
- Tamil-English code switching

### Phase 2: purpose-recorded pilot dataset

Collect 30-60 minutes of clean Tamil/Tanglish business speech. This is more valuable than several hours of uncontrolled online audio.

Recommended categories:

- Neutral conversation
- Customer support
- Sales and lead nurturing
- Empathy and apologies
- Questions and confirmations
- Money, dates, numbers, and percentages
- Names, places, URLs, and identifiers
- GST, EMI, CRM, KYC, OTP, and product terminology

### Phase 3: optional licensed-video ingestion

For 10-20 licensed videos of 10-15 minutes each:

```text
individual source videos
  -> extract audio per source
  -> standardize audio
  -> Demucs vocals/music separation
  -> VAD speech segmentation
  -> speaker verification
  -> remove guests and overlaps
  -> reject music residue, echo, clipping, laughter, and codec damage
  -> ASR draft transcript
  -> human transcript correction
  -> 2-12 second accepted clips
```

Do not concatenate everything into one giant training file. Each clip must retain its source provenance. Two to five hours of source video may leave only 45-150 minutes of genuinely clean speech after filtering.

### Phase 4: dataset construction

Each accepted manifest row contains:

```json
{
  "audio": "/data/accepted/clip_000001.wav",
  "text": "உங்க payment இன்னும் வரல சார்.",
  "speaker": "owned-voice-01",
  "language": "ta",
  "split": "train",
  "source_id": "recording-session-001",
  "rights_confirmed": true
}
```

Audio requirements currently enforced by the validator:

- Mono
- 24 kHz
- 16-bit PCM WAV
- 2-12 seconds
- Exact, non-empty transcript
- Unique clip path
- Train, validation, and test splits

Split by recording source/session. Do not put near-duplicate takes from the same session into both training and test.

### Phase 5: IndicF5 baseline

IndicF5 is the current Tamil-aware zero-shot candidate. It receives:

```text
target text
+ reference audio
+ exact reference transcript
-> generated Tamil speech
```

The repository includes `voice_training/scripts/benchmark_indicf5.py` and `voice_training/server.py`. Model access must be accepted on Hugging Face, and the model revision must be pinned.

Important limitation: AI4Bharat has not published an official IndicF5 fine-tuning recipe. Do not assume the upstream F5-TTS training scripts can safely load an IndicF5 checkpoint.

### Phase 6: conversational Tamil adaptation research

If the zero-shot model fails the held-out quality gate:

1. Establish a verified Tamil-compatible training path.
2. Confirm tokenizer coverage for Tamil and Latin characters.
3. Pin repository, checkpoint, dependency, and dataset revisions.
4. Train small controlled checkpoints.
5. Compare each checkpoint to the zero-shot baseline.
6. Reject checkpoints that damage general Tamil pronunciation.

Upstream F5-TTS experiments are tracked separately unless checkpoint compatibility with IndicF5 is proven.

### Phase 7: consented voice cloning/adaptation

Only after Tamil/prosody quality passes:

1. Record the owned/licensed speaker in a controlled room.
2. Begin with 30-60 minutes for an adaptation experiment.
3. Expand toward 3-6 clean hours for production consistency.
4. Preserve held-out speaker sessions.
5. Adapt speaker identity while monitoring Tamil regression.
6. Register a versioned voice profile such as `follei_owned_tamil_01_v1`.
7. Store consent evidence and enable the runtime consent gate.

Voice cloning teaches timbre, pitch range, breathiness, texture, and recurring cadence. Prosody controls should remain separate so support, sales, collections, and empathy do not all sound identical.

### Phase 8: production optimization

Once quality passes:

- Preload the model on a CUDA GPU server.
- Warm up inference before accepting calls.
- Stream PCM or telephony-compatible audio.
- Add a bounded TTS queue.
- Measure queue wait and inference separately.
- Add replicas or batching for concurrency.
- Cache approved common phrases.
- Load test one and ten concurrent calls.
- Test barge-in and rollback.

## 8. Evaluation and Acceptance

At least three fluent Tamil listeners should rate held-out samples from 1-5 for:

- Intelligibility
- Naturalness
- Spoken-Tamil accent
- Rhythm and pause placement
- Emphasis and emotional fit
- Tanglish code-switching
- Speaker similarity
- Business-entity pronunciation

Automatic and operational checks should include:

- Audio duration and corruption
- Long-sentence stability
- Missing or repeated words
- Train/test leakage
- Actual TTS provider and checkpoint revision
- Real-time factor
- Time to first audio
- GPU memory and queue depth
- Ten-call success/error rate

A checkpoint becomes `tamil-prosody-v1` only after it beats the current baseline and passes consent, entity, latency, concurrency, and rollback gates.

## 9. Latency Architecture

The user-visible metric is caller speech end to first meaningful Follei audio.

```text
VAD endpoint decision        150-350 ms
STT finalization             100-300 ms
controller/routing            20-80 ms
embedding/retrieval           20-100 ms
generation first token       200-600 ms
first speakable phrase       150-400 ms
TTS first audio              100-500 ms
target perceived start       approximately 0.8-1.8 s
```

These stages overlap. The current reported 4-15 seconds must be diagnosed from stage metrics; it may include STT finalization, retrieval, generation, TTS fallback, queueing, and client playback rather than TTS alone.

Latency improvements:

1. Stream STT partials but retrieve only when intent is stable.
2. Prefetch likely context, then perform final tenant-scoped retrieval at turn commit.
3. Stream LLM tokens.
4. Buffer semantic phrases instead of complete paragraphs or single words.
5. Keep TTS models warm.
6. Return first audio while later phrases are still generating.
7. Cache common approved acknowledgements.
8. Cancel stale work immediately on barge-in.

## 10. Ten-Call Architecture

Do not load ten copies of each model.

```text
Calls 1-10
  -> independent WebSocket/call state
  -> shared STT worker pool
  -> shared controller and retrieval services
  -> shared streaming generation service
  -> bounded TTS scheduler
  -> one or more warm GPU TTS workers
  -> per-call audio queues
```

The current IndicF5 baseline server serializes generation with an `asyncio.Lock`. This protects correctness for evaluation but is not a production ten-call scheduler. Production requires measured batching or multiple model replicas, queue limits, `429` overload responses, and call-level cancellation.

Active audio should remain on WebSocket/gRPC. Redis is appropriate for state and coordination, not every 20 ms PCM frame.

## 11. Required Deployment

Recommended initial topology:

```text
CPU application tier
  FastAPI, WebSockets, orchestration, VAD, normalization

Data tier
  PostgreSQL, Redis, Kafka, object storage, FerretDB, Qdrant

Generation tier
  hosted or dedicated streaming LLM

GPU speech tier
  streaming STT and Tamil TTS
```

The current development Mac has 8 GB RAM, integrated Intel graphics, and approximately 2 GB free disk at the time of inspection. It cannot train or production-serve this model. Use Linux CUDA infrastructure with at least 24 GB GPU memory for the first experiment and at least 100 GB persistent storage.

## 12. What Is Complete, Partial, and Missing

### Complete or present in code

- Multi-tenant FastAPI platform
- Knowledge ingestion and Qdrant retrieval
- Business-worker orchestration
- Lead and conversation analysis services
- WebSocket voice path
- ElevenLabs STT integration
- Streaming generation token handling
- Tanglish prompt policy
- Phrase buffering
- Barge-in cancellation
- Swappable TTS provider interface
- Follei model-server request adapter
- Dataset provenance and validation scripts
- IndicF5 benchmark script
- F5 CSV exporter
- Baseline IndicF5 server contract

### Partial or baseline only

- Romanized Tamil normalization: punctuation cleanup exists; contextual Roman-Tamil transliteration is not implemented.
- TTS streaming: WebSocket sends phrase audio chunks, but the baseline model server generates complete WAV per phrase.
- Concurrency: current baseline serializes TTS generation.
- Prosody parameters: request fields exist, but IndicF5 baseline does not independently implement all controls.
- Voice profiles: consent gates exist, but no trained named profile exists.

### Not completed

- No custom Tamil checkpoint
- No conversational Tamil fine-tune
- No consented cloned voice checkpoint
- No production Roman-Tamil model
- No ten-call GPU benchmark
- No telephony PCM streaming TTS implementation
- No listener MOS report
- No production model registry or rollback deployment

## 13. Immediate Next Actions

1. Preserve and separate the current dirty worktree before merging voice changes.
2. Obtain an owned/consented 10-30 second reference clip and exact transcript.
3. Accept IndicF5 model access and provision a CUDA machine.
4. Run the fixed baseline benchmark.
5. Have fluent Tamil listeners score the results.
6. Record the 30-60 minute purpose-built pilot corpus.
7. Build and validate the pilot manifest.
8. Decide from evidence whether zero-shot IndicF5 is sufficient or adaptation research is necessary.
9. Optimize and load test only after language quality passes.
10. Add a named voice profile only after explicit cloning rights and speaker evaluation.

## 14. Handover Files

Read these in order:

1. `docs/FOLLEI_PROJECT_AND_VOICE_HANDOVER_2026-08-31.md` - this verification handover.
2. `docs/FOLLEI_VOICE_AI_TRAINING_AND_RUNTIME_SPEC.md` - authoritative technical specification.
3. `voice_training/README.md` - executable dataset, benchmark, and model-server commands.
4. `app/api/websocket_handler.py` - current real-time voice orchestration.
5. `app/analysis/services/streaming_tts_service.py` - TTS provider boundary.
6. `app/analysis/services/tanglish_style.py` - Tanglish generation policy.
7. `voice_training/server.py` - IndicF5 baseline model-server contract.

## 15. Final Verification Statement

The repository has a credible architecture for tenant-grounded voice agents and now has a clear path to a custom Tamil speech system. The integration and training scaffolding are real; the custom model quality is not yet proven. Accent quality, natural Tamil, cloned identity, and ten-call capacity must be demonstrated through approved data, GPU experiments, held-out listener evaluation, and measured deployment tests before they are presented as completed capabilities.
