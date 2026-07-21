# Follei Systems 1 and 2 verification audit

Audit date: 2026-07-21 (Asia/Kolkata)

## Scope and scoring

This audit excludes the connectors the user explicitly removed from scope: Google Drive, OneDrive, SharePoint, Notion, Confluence, Gmail, Outlook, WhatsApp, Teams, Slack, CRM, ERP, LMS, accounting software, and ticketing platforms.

The strict evidence rubric remains:

- 0: absent
- 1: code only
- 2: passing automated proof
- 3: live service proof
- 4: production-hardening proof

| Scope | Rows | Points | Strict result | Distance to status 4 |
|---|---:|---:|---:|---:|
| System 1, excluding named connectors | 19 | 57/76 | **75.00%** | 25 percentage points |
| System 2 | 20 | 60/80 | **75.00%** | 25 percentage points |
| Combined requested scope | 39 | 117/156 | **75.00%** | 25 percentage points |

All 39 scoped capabilities have live status-3 evidence. The remaining 25% is production maturity, not a missing feature quarter. No row is status 4 because there is still no production backup/restore drill, HA/failover result, long load/soak result, formal security assessment, or alert-response record.

The two interfaces added in this pass do not change the proposal percentage because they are verification/product surfaces around the already-scored capabilities, not new System 1/2 rows.

## Current live result

### Runtime

```json
{"status":"healthy","services":{"api":"ok","postgres":"ok","redis":"ok","qdrant":"ok","kafka":"ok","ferretdb":"ok","object_storage":"ok"},"queues":{"indexing":{"queued":0,"processing":0,"retrying":0,"failed":0,"dead_lettered":1},"knowledge_sync":{"pending":0,"processing":0,"retrying":0}}}
```

The one dead-letter row is retained evidence from the intentional retry/DLQ test.

### Unified automated suite

```text
304 passed, 261 warnings in 34.78s
```

One `pytest -q` invocation collects the main, MCP, and AI tests with zero failures.

### Required tenant: three-store snapshot

Tenant: `87e38dbc-0218-4cd1-be7e-7d55721b2a07`

```json
{
  "postgres_documents": 13,
  "postgres_chunks": 434,
  "qdrant_points": 434,
  "ferretdb_documents": 13,
  "ready_in_all_three": 13,
  "job_statuses": {"indexed": 12},
  "structured": {"products": 3, "services": 1, "pricing": 0, "policies": 1, "plans": 0, "slas": 1},
  "graph_edges": 18
}
```

The verification API found no Qdrant or FerretDB read error. All 13 indexed PostgreSQL documents have Qdrant points and FerretDB projections.

### Refund chat gate: complete literal HTTP response

HTTP status: `200`

```json
{
  "answer": "```json\n{\n  \"answer\": {\n    \"refund_window\": {\n      \"duration\": \"45 days\",\n      \"start_point\": \"original purchase date\",\n      \"sources\": [\n        {\n          \"document\": \"refund_policy.docx (PAGE 0, paragraph)\",\n          \"content\": \"The refund window is 45 days from the original purchase date.\"\n        },\n        {\n          \"document\": \"APPROVED BUSINESS FACTS (Postgres)\",\n          \"content\": \"Documented policy: The refund window is 45 days from the original purchase date.\"\n        },\n        {\n          \"document\": \"LONG-TERM DOCUMENT MEMORY (refund_policy.docx summary)\",\n          \"content\": \"Our refund policy allows requests within **45 days** of the original purchase date.\"\n        }\n      ]\n    }\n  },\n  \"missing_information\": {\n    \"exceptions\": \"The retrieved documents do not specify any exceptions to the 45-day refund window (e.g., product types, regions, or customer tiers beyond 'Enterprise customers receive priority support').\",\n    \"eligibility_criteria_details\": \"The retrieved documents mention refunds are 'subject to review and approval based on eligibility criteria,' but do not enumerate specific criteria.\",\n    \"priority_support_scope\": \"The retrieved documents state 'Enterprise customers receive priority support' but do not define what this entails.\"\n  }\n}\n```",
  "citations": [
    {"document_name":"refund_policy.docx","page":0,"chunk_id":"7b60bb2d-4707-4b52-ab63-cc37a40567ed","heading":null,"source":"qdrant_chunk"},
    {"source":"postgres_fact","fact_id":"a58020d2-701f-4be2-af1c-a9f075dbf5c1","fact_type":"policy","topic":"Documented policy","citation":{"document_id":"fa8ad941-66da-4a8f-92bc-405214ddfd6d","document_name":"refund_policy.docx","chunk_id":"7b60bb2d-4707-4b52-ab63-cc37a40567ed","page":0,"heading":null,"heading_path":[],"source_uri":"verification://refund-policy","version":1}},
    {"source":"ferretdb_document_memory","document_id":"fa8ad941-66da-4a8f-92bc-405214ddfd6d","document_name":"refund_policy.docx","category":"policy","projection_type":"indexed_document_summary","freshness_at":"2026-07-20T09:49:34.331101+00:00","trust_rank":4}
  ],
  "confidence": 0.7,
  "supported": true,
  "reason": "Grounded answer produced from retrieved context; LLM verification disabled for the fast path.",
  "conversation_id": "b17d6639-8f8c-4f80-b78f-9ff3a922a14d",
  "conflicts": []
}
```

Gate result: pass. The answer contains `45 days`, `supported` is true, and the citations include the semantic chunk, canonical PostgreSQL fact, and clean FerretDB document-memory projection.

## System 1 finding

The scoped inputs are live-proven: websites, PDFs, brochures, product catalogs, SOPs, sales decks, and pricing sheets. The loaders also support DOCX, TXT, CSV, XLSX, PPT/PPTX, EML/MSG bodies, images, scanned-PDF OCR, and layout-aware chunks.

Every upload becomes its own durable Kafka indexing job. The new tenant interface submits selected files concurrently with `Promise.all`, while Kafka workers control processing and retry. This is preferable to serializing by file extension: a large PDF cannot block an unrelated XLSX, and each file has an independent job ID, retry count, disposition, and DLQ state.

Successful indexing has three distinct outputs:

| Store | Purpose | Verification shown at `/tenant` |
|---|---|---|
| PostgreSQL | Canonical document/chunks, reviewed Products, Services, Pricing, Policies, Plans, SLAs, provenance, and graph | document ID, lifecycle, category, version, chunk count, structured counts, graph edges |
| Qdrant | Tenant-filtered semantic chunk vectors | point count, approval states, source types, categories |
| FerretDB | Clean document/conversation long-term memory projection | summary projection, keywords, category, version, chunk count, freshness |

The browser-verified `/tenant` result displayed 13 document rows, 13 `all three` consistency badges, 18 graph edges, and 12 recent indexing jobs for the required tenant.

## System 2 finding

All scoped System 2 layers are status 3:

1. Structured knowledge: Products, Services, Pricing, Policies, Plans, dedicated SLAs.
2. Vector knowledge: Documents, Emails, PDFs, Call Transcripts, Knowledge Articles, semantic retrieval.
3. Graph: Product → Feature → Benefit → Customer Segment → Objection → Response.
4. Memory: long-term company/document memory, mid-term customer history, short-term active conversation context.

Retrieval combines PostgreSQL BM25/approved facts/graph relations, Qdrant dense vectors, and FerretDB memory. It does not treat the three databases as interchangeable copies.

## Interfaces delivered

### `http://127.0.0.1:8000/tenant`

- Existing Follei account login; token kept in tab-scoped `sessionStorage`.
- Multi-file drag/drop and category selection.
- Authorized bounded website URL ingestion.
- Independent upload job state.
- Live tenant-scoped PostgreSQL/Qdrant/FerretDB matrix.
- Structured knowledge counts, graph edge list, and indexing job list.
- No database credentials, API keys, or raw secrets are exposed.

### `http://127.0.0.1:8000/user`

- Authenticated tenant session and tenant-bound WebSocket.
- Microphone WAV capture, audio-file upload, and typed fallback.
- ElevenLabs STT language detection and multilingual TTS reply.
- Generic knowledge assistant, SDR, Sales Executive, and Support dispatch.
- Six lead scores, text sentiment, voice emotion, emotion fusion, BANT, and MEDDIC.
- Reply audio is queued sentence-by-sentence and autoreplies through the same grounded/worker path.

Browser verification sent `Hello` through the page and received two spoken reply chunks (`Hi.` and `How can I help you?`), six non-null scores, BANT/MEDDIC zeroes backed by the absence of qualification evidence, and `source: evidence_heuristic`. There were no browser console errors.

## Voice, six metrics, BANT, MEDDIC, and repository lineage

The canonical Follei implementation is not running the external repository wholesale:

- External audited commit: `2e40796ba990144b4b67dfa123c6bdc37a86bda7`.
- Canonical lead-intelligence implementation entered Follei in commit `c9e2afa573aa8b4e6e8b11cafbac7f598d0b0eae`.
- The canonical and external lead-intelligence file SHA-256 hashes are different.
- Follei uses its own tenant-scoped PostgreSQL/Qdrant/FerretDB contracts and workers; it does not use the external Chroma runtime.
- The external repository's wholesale merge gate remains failed. Its algorithm family was adapted into Follei-native services; the external callable service was not adopted.

Current behavior is deliberately split:

- Voice audio feeds STT, voice emotion, sentiment/emotion fusion, the Relationship score, overall lead confidence/conversion features, and spoken reply.
- ICP, Intent, Engagement, Qualification, and Buying Signal remain transcript/business-evidence signals. Tone does not change company fit or invent buying facts.
- BANT and MEDDIC use transcript and conversation evidence, not tone.
- When the optional local qualification GGUF is absent, BANT/MEDDIC now return evidence-only heuristic values instead of null. Zero means “no evidence in this transcript,” not “confirmed absent.”

Direct live speech proof:

```json
{
  "tts_bytes": 54378,
  "stt": {
    "text": "I need a product demo this quarter and I have an approved budget.",
    "language": "eng",
    "language_probability": 0.9677519202232361,
    "provider": "elevenlabs",
    "model": "scribe_v2"
  },
  "normalized_reply_language": "en",
  "emotion": {"emotion": "neutral", "confidence": 0.402954},
  "sample_rate": 16000,
  "audio_samples": 50079
}
```

The provider's ISO-639-3 codes are normalized to the ISO-639-1 codes used by RAG and TTS. English, Tamil, Hindi, Telugu, Malayalam, Kannada, Marathi, Bengali, Gujarati, Punjabi, Spanish, French, German, Portuguese, Arabic, Chinese, Japanese, Korean, and Russian mappings are present.

## Remaining work outside the functional scoped systems

Systems 1 and 2 are functionally complete at strict status 3 for this scope. Reaching status 4 requires operational evidence:

1. Backup and restore drill covering PostgreSQL, Qdrant, FerretDB, and object storage.
2. HA/failover exercise for API, queues, and stores.
3. Representative concurrent multi-file and chat load test plus a long soak.
4. Formal security review including WebSocket/session revocation and penetration testing.
5. Metrics, alert thresholds, paging, runbooks, and a recorded incident-response exercise.

The named external connectors remain excluded and are not counted as unfinished work in the 75% scoped result.
