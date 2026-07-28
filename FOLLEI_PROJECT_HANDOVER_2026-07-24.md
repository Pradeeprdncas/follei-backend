# Follei project handover

Prepared: 24 July 2026 (Asia/Kolkata)

## 1. Executive status

Follei is a tenant-aware autonomous business workforce backend. Its strongest working path is now:

1. Import business knowledge or lead files.
2. Extract structured records into PostgreSQL.
3. retain flexible/raw lead and conversation memory in FerretDB.
4. index approved knowledge and crawled content in Qdrant.
5. retrieve the three data layers together.
6. use that context in chat or real-time voice.
7. run SDR, Sales, or Support behavior and persist both sides of the conversation.

Current completion must be described at three different levels:

| View | Current estimate | Meaning |
|---|---:|---|
| Core local MVP path | 70–75% | Knowledge ingestion, lead import, pre-nurturing, three-store retrieval, tenant UI, local chat/voice, and three workers are substantially functional locally. |
| Full Version 1.0 proposal | about 38% strict maturity | Evidence-weighted estimate across all 239 proposal capabilities. The last complete row audit was 27.61% on 20 July; substantial lead, voice, model, and worker work has landed since then, but a new 239-row acceptance run has not been completed. |
| Production readiness | about 30% | Local functionality is ahead of operational readiness. Backups, failover, load/soak, formal security review, real-provider certification, and operational alerting are not complete. |

The percentage is not a simple count of files. The strict rubric is:

- 0: absent
- 1: code/scaffold only
- 2: automated test evidence
- 3: live local service evidence
- 4: production-hardened and operationally proven

No major subsystem should currently be called status 4.

## 2. Fresh verification snapshot

Verified on 24 July 2026:

- Branch: `main`
- Current committed revision: `4a69b071 recent code for folleibackend`
- `python -m pytest -q`: **332 passed, 261 warnings**
- API health: healthy
- PostgreSQL: healthy
- Redis: healthy
- Qdrant: healthy
- Kafka: healthy
- FerretDB: healthy
- S3-compatible object storage: healthy
- `/tenant`: HTTP 200
- `/user`: HTTP 200
- Indexing queues: no queued, processing, retrying, or failed jobs
- One dead-lettered indexing job remains from an intentional missing-file/retry test

Important handover warning: the working tree contains many uncommitted changes and new files, including the recent lead, voice, local-model, and revenue-intelligence work. The implementation is running, but the current state is not safely checkpointed in Git yet.

## 3. Storage architecture

PostgreSQL is the system of record for canonical, relational, transactional data:

- tenants and users
- leads and structured lead fields
- import jobs and import rows
- documents, chunks, versions, and approval state
- conversations and messages
- BANT/MEDDIC and lead scores
- operational business facts
- jobs, provenance, and workflow state

FerretDB is the flexible memory layer:

- raw and irregular imported lead fields
- source-row payloads
- lead memory and accumulated qualification evidence
- user and AI nurture turns
- crawled-page memory projections
- document summaries and evolving contextual facts

Qdrant is the semantic retrieval layer:

- document chunks
- approved business knowledge
- crawled website evidence
- tenant-filtered vector retrieval

Object storage retains uploaded source files. Redis supplies cache/runtime support. Kafka supplies durable indexing and synchronization work.

FerretDB is not a replacement for every PostgreSQL row. The intended design is canonical structure in PostgreSQL, flexible memory in FerretDB, and searchable vectors in Qdrant.

## 4. System-by-system checkpoint

| Scope | Status | What works | Main gaps |
|---|---|---|---|
| System 1 — Business Intelligence | **Mostly complete locally; 75% strict for the connector-excluded scope** | Multi-format upload, category-aware processing, OCR, bounded website crawl, Kafka jobs, review/publish, PostgreSQL/Qdrant/FerretDB projection, tenant verification UI | Live external connectors, unrestricted/deep media crawling, production hardening |
| System 2 — Knowledge | **Mostly complete locally; 75% strict** | Structured facts, vectors, graph relations, long/mid/short-term memory, hybrid retrieval, citations, approval filtering, conflicts, tenant isolation | Broader graph quality, large-scale performance proof, backup/failover/security evidence |
| System 3 — Revenue Intelligence | **Partial; roughly 40–50%** | Six lead metrics, BANT, MEDDIC, evidence accumulation, revenue score, lead scoring worker, persistence and UI delivery | SPIN/CHAMP/ANUM/custom frameworks, calibrated conversion probability, historical-deal training/evaluation, model monitoring |
| System 4 — Customer Intelligence | **Early; roughly 15–20%** | Customer schemas/models, events, renewals, health/churn/expansion fields | Current customer routes are largely in-memory/fixed; no real health, churn, adoption, payment-risk, renewal, upsell, or cross-sell engines |
| System 5 — AI Workforce | **Partial; roughly 30–35%** | Dispatchable SDR, Sales, and Support workers; SDR-to-Sales handoff; grounded responses; qualification, proposal and escalation tests | Customer Success, Collections, Account Manager, Executive Insights; real provider actions; full multi-worker workflow orchestration |
| System 6 — Learning | **Scaffold only; roughly 10–15%** | Durable `learning_signals` model/migration and existing interaction/outcome records | No complete action → response → outcome → measurement → model-update service; no proven online/offline learning loop |
| Communication | **Partial; roughly 45%** | Website chat, browser microphone streaming, real-time STT events, VAD, barge-in, streamed local generation, phrase-streamed TTS | Real phone calls, production WhatsApp/email/SMS delivery, provider receipts/retries, receptionist workflow |
| AI/model layer | **Partial; roughly 45–50%** | Local Qwen generation, intent/sentiment/topic/entity services, STT/TTS path, BANT/MEDDIC, revenue metrics, RAG and memory | Conversion/churn/upsell/payment/deal-risk models, formal accuracy evaluation, model lifecycle and drift monitoring |
| Analytics | **Early; roughly 10–15%** | Request/latency instrumentation and some stored operational metrics | Several analytics routes still return zero/default values; pipeline, forecast, velocity, win rate, retention, renewal and AI-revenue attribution are incomplete |
| Industry packs | **Not started** | Generic schemas can support later specialization | No Education, Healthcare, Real Estate, or Manufacturing pack implementation |
| North Star Revenue Influence | **Not implemented** | A conversation-level revenue score now exists | No attribution of influenced revenue across Sales, Support, Renewals, Collections, and Upsells |

## 5. Completed or substantially working workflows

### Knowledge intake and verification

- Upload PDF, DOCX, TXT, CSV, XLSX, PPTX, email bodies, images, and scanned PDFs.
- Select a knowledge category.
- Extract category-aware structured facts.
- Review and approve facts.
- Store canonical data in PostgreSQL.
- synchronize semantic chunks to Qdrant.
- project flexible document memory to FerretDB.
- inspect processing and three-store consistency from `/tenant`.

### Lead import and pre-nurturing

- Upload CSV, spreadsheet, PDF, DOCX, text, or supported image.
- Create a durable import job and preview extracted leads.
- Commit structured lead fields to PostgreSQL.
- retain original and irregular fields in FerretDB.
- discover URLs from lead data.
- crawl authorized URLs.
- index crawled material and update pre-nurturing state.
- display extracted leads, processing state, crawl state, and lead details in the tenant UI.

The earlier `lead_import_jobs does not exist` failure is addressed by the `20260722_lead_import_jobs.py` migration. A new environment must still run `alembic upgrade head`.

### Consolidated lead view

The lead detail surface combines:

- PostgreSQL lead and conversation data
- FerretDB import, nurture, qualification, and crawl memories
- Qdrant evidence
- indexing/pre-nurturing state

Both the user message and AI response are persisted for nurture conversations. This is implemented for the current lead-memory path; it does not mean every table in PostgreSQL is duplicated into FerretDB.

### Real-time voice

- Browser AudioWorklet continuously sends audio frames.
- ElevenLabs real-time STT can emit partial and committed transcripts.
- partial text can update the UI and prepare retrieval.
- committed text becomes the authoritative user turn.
- VAD removes the need to press Stop for every utterance.
- barge-in cancels queued generation/audio when the user speaks again.
- the local Qwen model streams tokens.
- phrase buffering sends natural chunks to TTS before generation finishes.
- WebAudio schedules returned audio with reduced gaps.
- markdown markers are removed before speech.
- contextual fillers replace one repeated filler.
- Tanglish styling uses conversational Tamil with English business terms.
- UI latency cards report STT, generation, TTS, and end-to-end timing.

Current limitation: TTS is configured to use `gtts_fallback` (`gtts-co.in`) because ElevenLabs TTS is skipped in local settings. It works, but it is the largest latency/voice-quality bottleneck and is not the final production voice.

### AI workers

- Support: grounded FAQ/support answers and human escalation.
- SDR: qualification, nurture/discovery behavior, meeting intent, score-based handoff.
- Sales: product explanation, objections, proposal behavior, and deal progression.
- Orchestrator: dispatches Support, SDR, and Sales; other declared worker types are not dispatchable.

## 6. Partially implemented or not fully proven

- External Gmail, Outlook, Slack, Teams, WhatsApp, CRM, and ERP connectors have code and mocked tests in several cases, but no current live OAuth/provider certification.
- Email, SMS, WhatsApp, and telephone delivery are not proven end to end.
- Lead imports and crawl flows have automated coverage and prior live UI proof, but should receive a clean acceptance run with a new tenant and representative files before release.
- Voice has component tests and local runtime behavior, but no formal latency/accuracy benchmark report across devices, languages, and network conditions.
- Learned BANT artifacts can be loaded, with LLM/rule fallback, but the conversion model does not yet have a sufficiently large labeled evaluation set.
- Customer routes currently use process-local dictionaries and fixed score calculations; they are not a durable Customer Intelligence system.
- Campaign domain code is minimal and does not yet represent a production campaign engine.
- Observability health is useful, but several analytics endpoints return placeholder zeros.
- Deprecation warnings remain around Pydantic configuration, FastAPI startup events, `datetime.utcnow()`, and some third-party libraries.

## 7. Remaining checkpoints in recommended order

### Checkpoint 0 — Preserve the current implementation

Acceptance criteria:

- review the dirty worktree
- remove or deliberately retain debug audio files
- confirm `.env` secrets are excluded
- commit the current coherent feature set
- tag or branch the verified state
- rerun `python -m pytest -q` and retain the result

### Checkpoint 1 — Clean end-to-end acceptance

Acceptance criteria:

- create a fresh tenant
- upload every supported knowledge format
- import representative CSV/XLSX/PDF/DOCX lead files
- verify structured PostgreSQL records
- verify FerretDB raw/nurture/crawl memories
- verify Qdrant points and retrieved evidence
- crawl authorized lead URLs
- complete one SDR → Sales voice journey
- restart services and verify data/session continuity
- remove the intentional old dead-letter record or label it clearly in the UI

### Checkpoint 2 — Voice latency and quality

Acceptance criteria:

- benchmark first STT partial, STT commit, first LLM token, first TTS audio, and total answer
- run at least English, Tamil, and Tanglish test sets
- activate and compare ElevenLabs streaming TTS against gTTS
- tune phrase boundaries and filler cancellation
- confirm markdown is never spoken
- confirm no audible inter-phrase gaps
- define p50/p95 latency targets

### Checkpoint 3 — Revenue Intelligence completion

Acceptance criteria:

- define labeled evaluation datasets
- validate six metrics, BANT, and MEDDIC against human labels
- add SPIN, CHAMP, ANUM, and tenant-defined frameworks
- implement calibrated conversion probability using historical, behavioral, intent, and qualification inputs
- record model version, confidence, evidence, and drift

### Checkpoint 4 — Real channels and integrations

Acceptance criteria:

- choose production providers
- complete OAuth/secrets handling
- prove real inbound/outbound email
- prove real WhatsApp text/media
- prove SMS delivery and receipts
- prove inbound/outbound telephone calls
- add idempotency, retry, webhook verification, rate limits, and delivery audit logs

### Checkpoint 5 — Customer Intelligence and remaining workers

Acceptance criteria:

- replace in-memory customer APIs with PostgreSQL repositories
- implement health, churn, adoption, renewal, expansion, and payment-risk engines
- implement Customer Success, Collections, Account Manager, and Executive Insights workers
- connect each worker to real actions and human approvals

### Checkpoint 6 — Learning, analytics, and attribution

Acceptance criteria:

- capture action, response, outcome, and performance signals automatically
- implement an offline evaluation/update pipeline with rollback
- replace placeholder analytics with database-backed calculations
- implement revenue pipeline, forecast, sales velocity, win rate, retention, renewal, and churn analytics
- implement the Revenue Influence Score and channel/worker attribution

### Checkpoint 7 — Production hardening

Acceptance criteria:

- backup and restore drill for every stateful store
- HA/failover verification
- load, soak, and concurrency tests
- tenant-isolation/security assessment
- secret rotation and least-privilege review
- dashboards, paging, runbooks, SLOs, and incident exercises
- deployment and rollback rehearsal

## 8. How to run and resume

From the repository root:

```powershell
.\start.bat
```

If the database is new or migrations changed:

```powershell
follei_backend\indic_tts_venv\Scripts\alembic.exe upgrade head
```

Primary local surfaces:

- `http://127.0.0.1:8000/tenant`
- `http://127.0.0.1:8000/user`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/health/`

Verification command:

```powershell
follei_backend\indic_tts_venv\Scripts\python.exe -m pytest -q
```

## 9. Immediate next decision

Do not start another broad feature batch before Checkpoints 0 and 1. The best next milestone is a clean, repeatable acceptance run for one fresh tenant covering knowledge upload, lead import, pre-nurturing crawl, three-store verification, lead detail, and an SDR-to-Sales voice conversation. That will convert the current large local implementation into a reliable handoff baseline.
