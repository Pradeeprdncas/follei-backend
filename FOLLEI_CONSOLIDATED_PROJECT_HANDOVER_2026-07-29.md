# Follei consolidated project handover

Prepared: 29 July 2026 (Asia/Kolkata)  
Repository: `D:\pradeep-coirei\Follei-backend-Team`  
Current branch: `main`  
Current revision: `33a0a78c6dda906e8aaddc380365472d8bb01840` — `current version of follei`  
Working tree at review time: clean

## 1. Main product goal

Follei's goal is to become a multi-tenant autonomous business workforce platform that learns a tenant's business knowledge, understands every lead and customer, communicates through text and voice, and uses specialized AI workers to sell, support, retain, collect, and grow revenue.

The main end-to-end product path is:

1. A tenant uploads business documents, websites, and lead files.
2. Follei extracts structured records, raw context, and searchable evidence.
3. PostgreSQL keeps canonical transactional data.
4. FerretDB keeps flexible lead, customer, document, and conversation memory.
5. Qdrant keeps tenant-filtered semantic evidence.
6. The system combines those stores to understand a lead or customer.
7. AI workers use that context in chat, voice, and eventually external channels.
8. User messages, AI responses, qualification evidence, actions, and outcomes are retained.
9. Future learning and analytics should improve actions and measure revenue influenced by Follei.

The immediate delivery goal is narrower than the full proposal: make one complete, repeatable local journey work for a fresh tenant:

`business knowledge → lead import → URL pre-nurturing → three-store verification → lead detail → SDR/Sales conversation → persistent qualification and conversation history`

## 2. Executive status

Follei is a substantial local backend, not a dummy-only application. Its strongest areas are knowledge ingestion, organizational memory, lead import, authorized website crawling, grounded retrieval, and the browser-based voice/chat journey.

The platform is not yet production-ready. It still mixes real implementations, AI-assisted flows, deterministic heuristics, in-memory/demo APIs, and unfinished workers.

| Measurement | Current estimate | Meaning |
|---|---:|---|
| Core local MVP | 70–75% | The primary knowledge, lead, memory, UI, and local conversation paths are substantially implemented. |
| Full Version 1.0 proposal | Approximately 38% | Customer Intelligence, the remaining AI workforce, campaigns, learning, analytics, industry packs, and revenue attribution remain far behind the core path. |
| Production readiness | 30–35% | Security, live-provider certification, durability, operations, performance, and disaster recovery remain incomplete. |

No major subsystem should currently be described as fully production-complete.

## 3. Actual technology stack

| Layer | Current implementation |
|---|---|
| Frontend | Static HTML, CSS, and JavaScript served by FastAPI |
| Backend | Python, FastAPI, Uvicorn, Pydantic |
| Relational database | PostgreSQL with SQLAlchemy and Alembic |
| Flexible memory | FerretDB |
| Semantic search | Qdrant |
| Cache/runtime | Redis |
| Events and background processing | Kafka consumers and direct asynchronous services |
| Source-file storage | MinIO/S3-compatible storage |
| Local response model | Qwen3-4B GGUF through llama.cpp |
| Embeddings | Mistral embedding API |
| Realtime STT | ElevenLabs Scribe |
| TTS | ElevenLabs implementation with gTTS fallback; current local path commonly uses gTTS |
| Web ingestion | `aiohttp`, BeautifulSoup, and Playwright fallback |
| Document processing | PDF, DOCX, PPTX, spreadsheet, email, text, image, and OCR libraries |
| Tests | Pytest |

The proposal's React/Next.js, Temporal, ClickHouse, LightGBM, complete omnichannel platform, industry packs, and Revenue Influence Score are not currently implemented.

## 4. Storage ownership

The three main databases have different jobs and should not contain identical copies of everything.

### PostgreSQL — canonical system of record

- tenants and users
- structured leads and customers
- lead import jobs and import rows
- documents, chunks, facts, versions, and approval state
- conversations and messages
- BANT, MEDDIC, lead scores, and workflow state
- provenance, jobs, and transactional records

### FerretDB — flexible business memory

- original and irregular lead fields
- complete source-row payloads
- accumulated lead qualification evidence
- nurture history containing user and AI turns
- crawled website/document memory
- flexible customer and tenant context
- evolving contextual summaries

### Qdrant — semantic evidence

- approved document chunks
- crawled website evidence
- lead-related indexed material
- tenant-filtered semantic retrieval payloads

MinIO retains uploaded source files, Redis supports caching/runtime behavior, and Kafka handles asynchronous indexing and synchronization.

## 5. What is working

### 5.1 System 1 — business knowledge ingestion

Substantially working locally:

- upload PDF, DOCX, TXT, CSV, XLSX, PPT/PPTX, email, image, and scanned files
- retain source files in object storage
- create durable indexing jobs
- process jobs through Kafka
- select and apply a knowledge category
- parse documents and run OCR
- extract category-aware structured facts
- review and approve facts
- store canonical content in PostgreSQL
- index semantic chunks in Qdrant
- project clean document memory into FerretDB
- crawl authorized websites with bounded, same-site collection
- use Playwright when basic HTML retrieval is insufficient
- discover supported downloadable website documents
- inspect processing and storage through the tenant console

The crawler deliberately uses page, size, domain, timeout, extension, and authorization limits. These are safety controls rather than defects.

### 5.2 System 2 — organizational knowledge and memory

Substantially working locally:

- PostgreSQL structured facts and relations
- FerretDB document, tenant, lead, and conversation memory
- Qdrant vector retrieval
- lexical/BM25-style retrieval
- hybrid retrieval and reranking
- approval filtering
- tenant filtering in the main knowledge and lead paths
- citations
- conflict surfacing
- lead-context injection into generated answers
- persistence of both the user message and AI response in the main nurture path
- a PostgreSQL outbox for retryable cross-store synchronization

### 5.3 Lead import and pre-nurturing

Substantially working locally:

- upload CSV, spreadsheet, PDF, DOCX, text, and supported images
- create a durable `lead_import_jobs` record
- extract, normalize, validate, deduplicate, and preview lead rows
- commit structured lead fields to PostgreSQL
- retain complete and irregular source data in FerretDB
- discover URLs contained in lead data
- require crawl authorization confirmation
- crawl authorized lead URLs
- send crawled content through the standard indexing pipeline
- reflect pre-nurturing status in PostgreSQL and FerretDB
- display leads, import jobs, crawl state, and three-store evidence in `/tenant`

The earlier `relation "lead_import_jobs" does not exist` error was addressed by the lead-import migration. Every new database must still run all Alembic migrations.

### 5.4 Consolidated lead detail

The tenant lead-detail view can combine:

- PostgreSQL structured lead data
- conversations and analysis
- import provenance and source rows
- FerretDB complete import memory
- FerretDB qualification and nurture memory
- FerretDB crawled-document memory
- Qdrant lead-scoped semantic evidence
- crawl and indexing status

This is the foundation for the requested single API/UI view of everything known about a lead.

### 5.5 Grounded local chat and browser voice

Implemented:

- browser `AudioWorklet` audio streaming
- realtime STT partial and committed transcript events
- VAD-based endpoint behavior
- barge-in and cancellation
- local Qwen token streaming
- RAG and lead-memory context injection
- phrase buffering for early TTS
- WebAudio playback
- removal of markdown markers before speech
- contextual filler selection instead of one literal filler
- conversational Tanglish prompting
- latency telemetry in the UI
- persistence of user and assistant turns

Current runtime limitation:

- the repository status page records exhausted ElevenLabs quota until 10 August 2026
- gTTS can provide TTS fallback, but there is no equivalent completed offline STT fallback
- gTTS is slower and does not provide the intended premium Tamil/Tanglish voice quality

### 5.6 Revenue qualification and current AI workers

Working at a partial maturity level:

- BANT analysis
- MEDDIC analysis
- six lead metrics
- evidence accumulation
- revenue-evidence scoring
- lead-scoring persistence
- SDR worker
- Sales worker
- Support worker
- SDR-to-Sales handoff behavior
- grounded response generation
- support escalation state

These flows use a mixture of local Qwen analysis and deterministic fallbacks. Several displayed scores are heuristic formulas, not trained predictive models.

### 5.7 Frontend surfaces

Working local surfaces:

- `/tenant` — tenant sign-in, knowledge ingestion, lead import, processing, lead lists, lead detail, and three-store inspection
- `/user` — browser chat/voice interaction and timing information
- `/docs` — generated API documentation
- `/health/` — local health endpoint

The frontend is implemented as static FastAPI-served HTML/JavaScript, not the React/Next.js application described in the proposal.

## 6. What is partial

### Email

Substantial provider code exists:

- Gmail IMAP polling and SMTP replies
- Brevo transactional email
- inbound email-shaped support workflow
- webhook secret handling
- loop and self-send protections
- provider health and adapter code
- Gmail and Outlook connector code

It is not production-certified because the standard startup does not launch the Gmail auto-reply worker, most provider evidence is mock-based, and durable receipt, bounce, complaint, retry, OAuth-lifecycle, and outage handling have not been proven.

### SMS

Provider implementation exists:

- Twilio client and webhook validation
- Twilio auto-reply orchestration
- Brevo transactional SMS
- number normalization and provider selection

It is not production-certified. A legacy `SmsProviderStub` remains, the general communication worker is unfinished, and live carrier delivery, receipts, consent, STOP/HELP, retries, and monitoring have not been proven.

### Revenue Intelligence

BANT, MEDDIC, lead metrics, and evidence scoring work, but:

- SPIN, CHAMP, ANUM, and tenant-defined frameworks are missing
- conversion probability is not calibrated from historical outcomes
- scores do not have a complete model/heuristic/fallback label everywhere
- multilingual evaluation and model monitoring are incomplete

### AI Workforce

SDR, Sales, and Support are dispatchable. Customer Success, Collections, Account Manager, and Executive Insights are not implemented as complete workers. Some “actions” only create an internal record instead of completing an external action.

### Customer Intelligence

Models and schemas exist, but current customer behavior remains early. Health, churn, adoption, renewal, expansion, satisfaction, and payment-risk intelligence are not complete durable engines.

### External integrations

There is connector and OAuth-oriented code for several services, but Gmail, Outlook, WhatsApp, CRM, ERP, Slack, Teams, calendars, and telephone providers have not received complete live multi-tenant certification.

### Analytics and learning

Health and latency instrumentation exist. A learning-signal model also exists. However, several analytics paths return zero/default values, and there is no complete:

`action → customer response → business outcome → evaluation → safe model update`

learning loop.

## 7. What is incomplete or placeholder

Verified unfinished worker bodies:

- campaign execution worker
- communication delivery worker
- CRM synchronization worker
- analytics aggregation worker
- standalone embedding worker
- standalone OCR worker

The campaign worker still contains:

```python
pass  # TODO: Implement campaign execution
```

Campaigns therefore do not yet have a complete CRUD-to-launch-to-delivery-to-analytics product workflow.

Other incomplete areas:

- real telephone inbound/outbound channel
- AI receptionist
- campaign segmentation, scheduling, consent, suppression, delivery, and analytics
- durable omnichannel outbox and reconciliation
- Customer Success, Collections, Account Manager, and Executive workers
- calibrated conversion, churn, upsell, payment-risk, and deal-risk models
- production dashboards
- industry packs
- cross-lifecycle Revenue Influence Score
- high availability, disaster recovery, and operational certification

## 8. Hardcoded, heuristic, and dummy behavior

### Real model-backed behavior

- local Qwen answer generation
- local-Qwen-assisted business fact extraction
- local-Qwen-assisted BANT and MEDDIC
- Mistral embeddings
- ElevenLabs STT when quota and network are available
- small sentiment and experimental voice-emotion models

### Heuristic or manually configured behavior

- filler text and filler selection
- some quick-assistant answers
- SDR/Sales/Support intent classification
- six lead-metric weights
- revenue-evidence score
- conversion fallback
- qualification thresholds
- portions of Tanglish vocabulary

Deterministic safety, validation, routing, and fallback rules are appropriate. The problem is only when a heuristic is presented as trained prediction or as a completed real-world action.

### Placeholder or demo behavior that must not be treated as production

- general messaging SMS stub
- empty workers listed above
- fixed or in-memory behavior in parts of the customer, lead, conversation, integration, and tools APIs
- an agent chat route that does not represent the complete worker/RAG path
- analytics returning zero/default values
- integrations that can appear connected without a proven provider lifecycle

## 9. Critical security status

Production exposure is blocked until security isolation is completed.

Verified concerns in the current mounted application include:

- wildcard CORS
- inconsistent authentication across `/api/v1` routes
- tenant and user administration routes without complete authorization enforcement
- mounted generic database CRUD
- mounted legacy/demo domains alongside canonical services
- potential exposure of internal credential-shaped fields
- inconsistent tenant enforcement outside the main lead/knowledge paths
- development-secret and configuration hardening still required

The application should remain restricted to trusted local development until P0 security acceptance passes.

## 10. Current verification snapshot

Verified on 29 July 2026:

- branch: `main`
- revision: `33a0a78c6dda`
- working tree: clean
- current commit date: 28 July 2026
- campaign, communication, CRM-sync, analytics, embedding, and OCR worker TODOs still exist
- Docker Desktop Linux engine was not running
- infrastructure and API could therefore not be started for a fresh live acceptance run
- the full test command was attempted but did not finish within a five-minute bounded window while infrastructure was unavailable

Latest retained successful baseline from 24 July 2026:

- `332 passed`
- API and all required infrastructure were healthy
- `/tenant` and `/user` returned HTTP 200

The 24 July result is a retained baseline, not a fresh 29 July certification.

## 11. How to start the project

Prerequisites:

- Docker Desktop must be running with the Linux engine available
- `.env` must exist
- the repository virtual environment must exist
- Windows Terminal must be installed

From the repository root:

```powershell
.\start.bat
```

The startup script:

1. checks Python dependencies
2. installs/checks Playwright Chromium
3. starts PostgreSQL, Redis, Qdrant, MinIO, FerretDB, ZooKeeper, and Kafka
4. waits for infrastructure
5. initializes the base schema and runs Alembic migrations
6. starts the API and five active workers
7. verifies health, `/tenant`, and `/user`

Workers started by the standard runtime:

- indexing worker
- knowledge-sync worker
- conversation-analysis worker
- lead-scoring worker

The API itself is the fifth runtime tab. Campaign, communication, CRM-sync, and Gmail mailbox workers are not started by this standard runtime.

Verification command:

```powershell
follei_backend\indic_tts_venv\Scripts\python.exe -m pytest -q
```

## 12. Remaining work in recommended order

### Checkpoint 0 — restore and prove the baseline

- start Docker Desktop
- run `.\start.bat`
- confirm all required ports and services
- run all Alembic migrations
- run the complete automated suite without a timeout
- verify `/health/`, `/tenant`, `/user`, and `/docs`
- retain logs and the exact test result

Acceptance: a fresh developer can start the same committed revision and reproduce a healthy system.

### Checkpoint 1 — P0 security isolation

- remove or protect generic database CRUD
- enforce authentication globally on protected APIs
- enforce tenant scope on every tenant-owned record
- add role-based authorization
- remove hashes, secrets, and internal credentials from responses
- restrict CORS
- reject unsafe production defaults
- add unauthenticated and cross-tenant regression tests

Acceptance: an unauthenticated user cannot read or change business data, and tenant A cannot access tenant B.

### Checkpoint 2 — one clean end-to-end tenant acceptance

- create a fresh tenant and admin
- upload every supported business-knowledge format
- review and approve extracted facts
- import representative CSV/XLSX/PDF/DOCX leads
- verify PostgreSQL, FerretDB, and Qdrant separately
- authorize and run lead URL pre-nurturing
- inspect the consolidated lead view
- complete an SDR-to-Sales conversation
- restart everything and verify persistence

Acceptance: the full core journey works repeatedly without manual database repair.

### Checkpoint 3 — voice reliability and latency

- add local/offline STT fallback
- restore or replace the premium TTS path
- benchmark English, Tamil, and Tanglish
- measure STT partial, transcript commit, first LLM token, first audio, and total response
- report p50 and p95 latency
- remove audible inter-phrase gaps
- verify markdown is never spoken
- tune fillers and cancellation

Acceptance: voice remains usable during provider failure and meets agreed p50/p95 targets.

### Checkpoint 4 — Email and SMS production certification

- choose production providers
- start required workers automatically
- implement durable outbox and idempotency
- prove real inbound and outbound delivery
- store provider message IDs and delivery receipts
- handle retry, bounce, complaint, suppression, rate limit, consent, STOP, and HELP
- test provider outage and tenant isolation
- remove stub fallbacks from production routing

Acceptance: live messages, provider receipts, retries, and compliance are demonstrated and monitored.

### Checkpoint 5 — Campaign engine

- campaign CRUD
- audience filters and immutable recipient snapshots
- templates and personalization
- channel selection
- schedules and timezones
- consent, suppression, unsubscribe, and frequency caps
- implement `CampaignWorker._process()`
- delivery event ingestion
- retries and dead-letter handling
- open, click, reply, conversion, and unsubscribe metrics
- campaign UI and analytics

Acceptance: a tenant can create, launch, monitor, pause, and audit a real campaign.

### Checkpoint 6 — Revenue and Customer Intelligence

- label every score as model, heuristic, fallback, or human-reviewed
- build labeled evaluation datasets
- validate BANT, MEDDIC, and the six metrics
- add SPIN, CHAMP, ANUM, and custom frameworks
- train and calibrate conversion probability
- replace in-memory customer APIs with PostgreSQL repositories
- implement health, churn, adoption, renewal, expansion, and payment-risk engines

Acceptance: metrics are reproducible, evaluated, source-labeled, and based on durable customer data.

### Checkpoint 7 — complete the AI workforce and action loops

- Customer Success worker
- Collections worker
- Account Manager worker
- Executive Insights worker
- calendar event creation
- real proposal document generation
- CRM synchronization
- support-ticket creation
- human approvals for consequential actions

Acceptance: worker actions create verifiable provider-side results and retain provider IDs.

### Checkpoint 8 — learning, analytics, and attribution

- complete outcome collection
- create offline evaluation and safe update pipelines
- implement rollback and model-version tracking
- replace zero/default analytics
- add pipeline, forecast, velocity, win-rate, retention, renewal, and churn dashboards
- implement Revenue Influence Score and channel/worker attribution

Acceptance: Follei can show what it did, what happened afterward, and how revenue attribution was calculated.

### Checkpoint 9 — production hardening

- backup and restore drills for every stateful store
- high availability and failover
- load, soak, and concurrency testing
- secret rotation and least privilege
- observability, paging, runbooks, and SLOs
- security assessment
- incident, deployment, and rollback rehearsals

Acceptance: production release gates are documented, repeatable, and signed off.

## 13. Recommended immediate next action

Do not begin another broad feature batch first.

The next action should be:

1. start Docker Desktop,
2. run the committed baseline,
3. complete Checkpoint 0,
4. close P0 security,
5. execute one fresh end-to-end tenant acceptance.

That produces a secure and reproducible foundation. Email/SMS certification and campaign implementation should follow only after the canonical core path and tenant isolation are proven.

## 14. Handover summary

What Follei already does well:

- ingests business knowledge
- stores structured, flexible, and semantic data in the correct layers
- imports and enriches leads
- crawls authorized lead URLs
- exposes lead and storage evidence in the frontend
- performs grounded local generation
- supports realtime browser voice architecture
- persists user and AI conversation memory
- runs SDR, Sales, and Support behavior

What prevents completion:

- security isolation is incomplete
- several mounted domains remain demo/in-memory
- external communications are not production-certified
- campaign execution is absent
- Customer Intelligence is early
- four proposed AI worker roles are missing
- predictive scoring is mostly heuristic
- learning, analytics, and revenue attribution are incomplete
- production operations have not been certified

Follei's foundation is useful and real. The remaining work is primarily conversion from a strong local prototype into one secure, durable, provider-connected, measurable production system.
