# Follei Voice AI: Training and Runtime Specification

Status: implementation specification
Audience: Follei engineers, ML engineers, infrastructure engineers, and coding agents
Primary code: `app/api/websocket_handler.py`, `app/analysis/services/streaming_tts_service.py`, `voice_training/`

## 1. Objective

Follei must conduct natural business conversations in Tamil, Tanglish, and English while grounding every factual answer in the tenant's data. The voice system must keep language ability, conversational strategy, and speaker identity as separate concerns.

The desired result is:

1. Accurate understanding of spoken Tamil, Romanized Tamil, Tanglish, and English.
2. Answers grounded in the client's approved knowledge and customer/lead state.
3. Natural spoken Tanglish rather than literal or literary translation.
4. Human-like Tamil pronunciation, rhythm, pauses, emphasis, and conversational prosody.
5. A distinct owned or licensed voice identity.
6. Predictable behavior under one call and at least ten concurrent calls.

Do not treat "the voice model" as one model responsible for everything. Follei is a pipeline of specialized models and deterministic services.

## 2. System Components

Follei uses four model roles plus supporting services.

| Component | Responsibility | Input | Output |
|---|---|---|---|
| Streaming STT | Convert caller audio to partial and final text; identify language | PCM/audio frames | transcript, language, confidence |
| Conversation controller | Detect intent, lead stage, sentiment, objection, turn state, next action, and whether retrieval is needed | transcript and call state | structured control decision |
| Grounded generation model | Use tenant knowledge, conversation history, and strategy to generate the answer | control decision and retrieved context | streaming response text |
| Tamil TTS | Convert normalized Tamil/Tanglish text into speech | text and voice controls | audio chunks |
| VAD/turn detector | Determine speech start, speech end, and interruption | audio frames | turn events |
| Retrieval service | Retrieve tenant-scoped facts and documents | normalized query | ranked context |
| Lead-state service | Maintain qualification, nurture stage, objections, and next-best action | call events | durable lead state |
| Text frontend | Normalize punctuation and eventually Romanized Tamil | generated text | TTS-ready mixed Tamil text |

The conversation controller can initially be deterministic logic plus a small classifier. It does not need to be a large generative model. The grounded generation model may remain a hosted or local LLM, but it must stream tokens and respect tenant boundaries.

## 3. End-to-End Runtime Flow

```text
Caller audio
  -> voice gateway/WebSocket
  -> VAD and barge-in detection
  -> streaming STT partials
  -> language and turn finalization
  -> conversation controller
  -> tenant-scoped retrieval and lead state
  -> grounded generation model
  -> Tanglish response policy
  -> semantic phrase buffer
  -> speech text normalizer
  -> Tamil TTS service
  -> WAV/PCM/MP3 chunks
  -> caller
```

Operations must overlap. Do not wait for a complete response before starting TTS. Do not translate Tamil to English and back on every turn. Retrieval may be prefetched from a stable partial intent, but final retrieval must use the committed utterance.

The currently implemented WebSocket path is in `app/api/websocket_handler.py`. It streams generation tokens, buffers them into phrases, synthesizes each phrase, supports barge-in cancellation, and reports stage latency. The provider boundary is `TTSProvider` in `app/analysis/services/streaming_tts_service.py`.

## 4. Language and Tanglish Policy

The internal spoken representation should be Tamil script with English business terms preserved in Latin script:

```text
உங்க account-ல இன்னும் payment வரல சார்.
```

Prefer this representation over either extreme:

- Do not force all English loanwords into formal Tamil.
- Do not send fully Romanized Tamil to a model that classifies it as English.
- Do not generate literary or textbook Tamil for ordinary business calls.

The generation model currently receives Tanglish guidance from `app/analysis/services/tanglish_style.py`. The runtime cleaner is `app/analysis/services/speech_text_normalizer.py`. The cleaner deliberately does not claim to be a complete Roman-Tamil transliterator.

The target Roman-Tamil frontend must normalize spelling variants contextually:

```text
enna panringa
enna panreenga
enna pandringa
ena panringa
    -> என்ன பண்றீங்க
```

It must preserve names, product names, identifiers, and common English terms such as `account`, `payment`, `CRM`, `GST`, `EMI`, `KYC`, and `OTP`. This frontend should eventually be evaluated as its own model/service instead of being hidden inside TTS.

## 5. TTS Request Contract

The backend sends the following internal request to the selected TTS service:

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

### Parameter definitions

| Parameter | Type | Required | Meaning |
|---|---|---:|---|
| `text` | string | yes | Final TTS-ready Tamil/Tanglish text; plain text only |
| `language` | string | yes | Normalized language code, currently `ta` for the Follei Tamil server |
| `model` | string | yes | Versioned acoustic/prosody model identifier |
| `accent` | string | yes | Approved accent preset; not a person's identity |
| `prosody_profile` | string | yes | Delivery preset such as `conversational`, `support`, or `sales` |
| `voice_profile` | string/null | yes | Owned/licensed speaker identity; null uses the baseline reference voice |
| `speed` | float | yes | Speaking-rate multiplier; currently constrained to a safe range |

`model`, `accent`, and `prosody_profile` are explicit because they represent different concerns. A voice profile must not silently define the language model or business style.

The currently implemented model server accepts this schema at `POST /synthesize` in `voice_training/server.py`. The backend adapter is `FolleiModelTTSProvider`. It accepts either direct audio bytes with an `audio/*` content type or JSON containing Base64 audio.

### Future parameters

Add parameters only after the selected model can implement and test them. Candidate additions are:

```json
{
  "emotion": "empathetic",
  "pitch_semitones": 0.0,
  "output_format": "pcm_s16le",
  "sample_rate": 24000,
  "call_id": "call_123",
  "tenant_id": "tenant_123"
}
```

Do not add placeholder fields such as `is_someparameter` without defining type, default, validation, behavior, observability, and backward compatibility. Every binary setting must use a meaningful boolean name, for example `normalize_numbers: true`, not a generic `is_parameter` field.

### Response contract

The service should return:

- `200` with `audio/wav`, `audio/mpeg`, or the negotiated streaming format.
- A provider/model revision header for diagnostics.
- `400` for unsupported language, profile, or parameter combinations.
- `401` for an invalid internal service token.
- `422` for schema validation failures.
- `429` when the inference queue is full.
- `503` when the model is unavailable.

## 6. Current Configuration

The backend configuration lives in `app/config/settings.py`:

| Setting | Purpose |
|---|---|
| `SPEECH_TO_TEXT_PROVIDER` | Selects the STT provider |
| `TTS_PROVIDER` | Selects `elevenlabs` or the Follei model server |
| `FOLLEI_TTS_BASE_URL` | Internal model-server URL |
| `FOLLEI_TTS_API_KEY` | Internal bearer token |
| `FOLLEI_TTS_MODEL` | Acoustic/prosody model version |
| `FOLLEI_TTS_ACCENT` | Accent preset |
| `FOLLEI_TTS_PROSODY_PROFILE` | Default delivery profile |
| `FOLLEI_TTS_VOICE_PROFILE` | Optional consented voice profile |
| `FOLLEI_TTS_VOICE_CONSENT_CONFIRMED` | Required gate for a named voice profile |
| `FOLLEI_TTS_TIMEOUT_SECONDS` | TTS service timeout |

Current development defaults still route through ElevenLabs/gTTS unless `TTS_PROVIDER=follei` is configured. A benchmark must always record the actual provider because fallback audio must not be mistaken for the custom Tamil model.

## 7. Voice Data Policy

Only use audio that is owned by Follei or explicitly licensed for AI training, voice cloning, commercial deployment, and derivative synthesis. Public availability is not permission.

For every source retain:

- Source identifier and location.
- Speaker identifier.
- Rights basis and evidence location.
- Date and scope of consent/license.
- Whether commercial model training is permitted.
- Whether voice identity cloning is permitted.
- Withdrawal and deletion procedure.

The training manifest requires `rights_confirmed: true`. The runtime requires `FOLLEI_TTS_VOICE_CONSENT_CONFIRMED=true` before activating a named voice profile.

## 8. Dataset Preparation

Never concatenate all videos into one training file. Preserve source provenance and segment the accepted speech into short clips.

```text
owned/licensed recordings
  -> audio extraction
  -> mono/sample-rate standardization
  -> optional vocals/music separation
  -> VAD segmentation
  -> speaker verification
  -> overlap, music, echo, clipping, and noise rejection
  -> draft Tamil ASR
  -> human transcript correction
  -> 2-12 second PCM clips
  -> source-level train/validation/test split
  -> manifest validation
```

Music separation is not proof that a clip is clean. Reject residual music, guests, overlapping speech, laughter, strong room reverb, codec damage, and unnatural edits. Exact transcript alignment is mandatory.

The executable workflow is in `voice_training/`:

```bash
python voice_training/scripts/ingest_sources.py \
  voice_training/manifests/sources.jsonl \
  /data/follei-voice \
  --separate-vocals

python voice_training/scripts/validate_manifest.py \
  voice_training/manifests/clips.jsonl
```

## 9. Recording Composition

For the first meaningful evaluation, collect 30-60 minutes of exceptionally clean, consented speech. For a production identity, target 3-6 hours after filtering.

Recommended production composition:

| Category | Approximate share |
|---|---:|
| Neutral conversational Tamil/Tanglish | 20% |
| Customer support and explanation | 20% |
| Sales and lead nurturing | 15% |
| Empathy, apology, and reassurance | 15% |
| Questions and confirmations | 10% |
| Numbers, dates, currency, percentages | 10% |
| Names, places, URLs, identifiers | 5% |
| Abbreviations and product terminology | 5% |

Record multiple natural performances, but do not fabricate extreme emotions. Sessions should have consistent microphone placement and room characteristics. Split by recording session/source so near-duplicate takes cannot leak into the test set.

## 10. Model Training Strategy

### Stage A: zero-shot baseline

Benchmark `ai4bharat/IndicF5` with an owned 10-30 second reference clip and exact transcript. IndicF5 is currently the Tamil-aware baseline, not automatically the final production model.

Evaluate multiple owned/neutral references while keeping text prompts fixed. This separates Tamil/prosody quality from speaker identity quality.

### Stage B: conversational Tamil adaptation

Proceed only if the baseline fails pronunciation or prosody requirements and a compatible training path is established. AI4Bharat has not published an official IndicF5 fine-tuning recipe. Do not assume an upstream F5 checkpoint, tokenizer, and IndicF5 checkpoint are interchangeable.

An upstream F5-TTS experiment must therefore be tracked separately with:

- Pinned repository and checkpoint revisions.
- Proven Tamil and Latin character coverage.
- A custom dataset exported in official `audio_file|text` format.
- A reproducible configuration and seed.
- Validation loss plus listening evaluation.
- Evidence that Tamil ability improves rather than regresses.

### Stage C: owned speaker adaptation

Apply speaker adaptation only after the conversational Tamil model passes language tests. Use the owned speaker dataset to learn timbre and stable delivery without replacing Tamil knowledge. Compare checkpoints frequently for catastrophic forgetting.

### Stage D: production optimization

After quality passes, optimize inference independently: model compilation, quantization only when quality remains acceptable, warm model replicas, batching, audio caching, and streaming output.

## 11. Evaluation and Promotion

Never select a checkpoint from training loss alone. Use a held-out prompt suite and at least three fluent Tamil listeners.

Rate each sample from 1-5 for:

- Tamil intelligibility.
- Naturalness.
- Spoken-Tamil accent quality.
- Rhythm, pause placement, and emphasis.
- Tanglish code-switch pronunciation.
- Speaker similarity when applicable.
- Emotional appropriateness.
- Business-entity accuracy.

The entity suite must include money, decimals, dates, time, phone numbers, OTP, GST, EMI, CRM, KYC, URLs, plan identifiers, and Tamil/Indian names.

A checkpoint may become `tamil-prosody-v1` only if:

1. It beats the current baseline on the held-out suite.
2. There is no train/test source or session overlap.
3. Consent and provenance records are complete.
4. Critical entity errors are below the agreed threshold.
5. Long sentences do not collapse or hallucinate audio.
6. The service passes one-call and ten-call tests.
7. Rollback to the previous model revision is tested.

## 12. Lead Nurturing and Grounded Generation

The generation system must never use TTS to invent facts. TTS speaks only the answer produced by the grounded generation pipeline.

Each committed caller turn should produce or update a structured control decision similar to:

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

The generation model then receives:

- Tenant-scoped retrieved facts.
- Conversation summary and recent turns.
- Lead/customer state.
- Worker role such as SDR, sales, support, collections, or customer success.
- Allowed next-best action.
- Tanglish output policy.

It returns short, speakable text. The direct answer comes first. It should ask at most one useful follow-up question and avoid Markdown, bullet symbols, emojis, citations meant only for visual display, and long paragraphs.

## 13. Latency Design

The primary user metric is end-of-user-speech to first meaningful answer audio. Track complete turn latency separately.

Target budget:

| Stage | Target |
|---|---:|
| VAD endpoint decision | 150-350 ms |
| STT finalization | 100-300 ms |
| Controller/routing | 20-80 ms |
| Query embedding and retrieval | 20-100 ms |
| Generation first token | 200-600 ms |
| First speakable phrase | 150-400 ms |
| TTS first audio | 100-500 ms |
| Perceived response start | approximately 0.8-1.8 s |

These are engineering targets, not guarantees. Current 4-15 second behavior must be diagnosed from emitted stage metrics rather than attributed entirely to TTS.

Required metrics per turn:

- `stt_first_partial_ms`
- `stt_commit_ms` or `stt_ms`
- `controller_ms`
- `retrieval_ms`
- `first_token_ms`
- `first_phrase_ms`
- `tts_first_audio_ms`
- `total_ms`
- TTS provider, model revision, queue wait, generation time, audio duration, and real-time factor

## 14. Concurrency and Ten Calls

Do not load one model copy per call. Models remain resident in dedicated workers while each call keeps independent state and audio queues.

```text
Calls 1..10
  -> async voice connections
  -> per-call state and cancellation
  -> shared STT worker pool
  -> shared retrieval/generation services
  -> bounded TTS queue
  -> one or more warm GPU TTS workers
```

The current baseline server serializes IndicF5 generation with a lock for correctness. That is suitable for initial evaluation, not ten-call production. Production requires load testing to choose batching, replica count, GPU class, maximum queue depth, and overload behavior.

For common short phrases, approved audio may be pre-generated and cached. Do not repeatedly synthesize identical acknowledgements. Do not send every 20 ms PCM frame through Redis; keep active audio on WebSocket/gRPC and use Redis for state, coordination, and durable events.

On barge-in:

1. Detect caller speech.
2. Cancel queued and active response audio for that call.
3. Stop sending stale TTS chunks.
4. Commit the new caller turn.
5. Generate a new grounded response.

## 15. Deployment Topology

Initial deployment should separate responsibilities:

```text
CPU application tier
  FastAPI, WebSocket gateway, call state, VAD, normalization, orchestration

Data tier
  PostgreSQL, Redis, Qdrant/object storage

Generation tier
  hosted or dedicated streaming LLM

GPU speech tier
  streaming STT and Tamil TTS model servers
```

The current Intel Mac is a development machine only. It does not have sufficient GPU, RAM, disk, or dependencies to train IndicF5/F5-TTS. Training and load tests require a Linux CUDA environment and persistent external storage.

## 16. Coding-Agent Rules

When an AI agent works on Follei voice code, it must:

1. Read this document, `voice_training/README.md`, and the affected runtime files first.
2. Inspect `git status` and preserve unrelated user changes.
3. Distinguish implemented behavior from target architecture.
4. Never claim training completed without a checkpoint, logs, evaluation report, and model revision.
5. Never enable a named voice profile without documented consent and the runtime consent gate.
6. Never combine tenant data across tenants during retrieval, caching, logs, or evaluation.
7. Keep STT, controller, generation, normalization, and TTS behind separate contracts.
8. Pin model and repository revisions for reproducibility.
9. Validate datasets before GPU jobs and reject unapproved sources.
10. Add tests for schema changes, fallback behavior, language routing, content types, and cancellation.
11. Record actual provider/model metadata so fallback output cannot be misreported.
12. Preserve rollback compatibility when adding request parameters.

## 17. Delivery Phases

### Phase 1: baseline

- Collect an owned 10-30 second clean reference and exact transcript.
- Benchmark IndicF5 with `voice_training/eval/prompts.jsonl`.
- Connect the accepted baseline to the Follei adapter.
- Measure one-call latency and quality.

### Phase 2: dataset

- Record and transcribe 30-60 minutes of purpose-built Tamil/Tanglish business speech.
- Validate provenance, quality, and source-level splits.
- Expand the entity and conversational evaluation suites.

### Phase 3: adaptation research

- Establish a verified Tamil-compatible fine-tuning path.
- Run controlled checkpoints and listener evaluations.
- Promote only an objectively better conversational Tamil model.

### Phase 4: voice identity

- Expand the owned speaker corpus toward 3-6 clean hours.
- Adapt and evaluate identity independently from Tamil ability.
- Register a versioned, consented voice profile.

### Phase 5: production speech

- Add true streaming PCM or telephony-compatible audio.
- Add bounded GPU queues, warm replicas, batching, caching, and overload handling.
- Pass ten-call load, barge-in, failure, and rollback tests.

## 18. Definition of Done

The Follei Tamil voice system is production-ready only when it produces grounded, natural Tanglish with an owned voice; correctly pronounces the business entity suite; starts meaningful audio within the agreed percentile latency; handles ten concurrent calls without cross-call leakage; supports interruption; records model/provider diagnostics; and can roll back safely.

## 19. Primary Technical References

- IndicF5 model and usage: `https://huggingface.co/ai4bharat/IndicF5`
- IndicF5 source repository: `https://github.com/AI4Bharat/IndicF5`
- IndicF5 training-script status: `https://github.com/AI4Bharat/IndicF5/issues/16`
- F5-TTS training documentation: `https://github.com/SWivid/F5-TTS/blob/main/src/f5_tts/train/README.md`
- F5-TTS source repository: `https://github.com/SWivid/F5-TTS`
