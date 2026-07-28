# Follei implementation, hardcoding, dummy-code, and stack audit

Prepared: 24 July 2026  
Repository: `D:\pradeep-coirei\Follei-backend-Team`  
Proposal audited: Follei Autonomous Business Workforce Platform, Version 1.0

## 1. Executive verdict

Follei is not a completely dummy application. The knowledge ingestion, three-store knowledge architecture, lead-import persistence, bounded website crawling, grounded retrieval, local answer generation, and browser voice transport contain substantial working implementations.

It is also not yet a consistently real autonomous workforce platform. The repository mixes five different implementation levels:

1. Real, persisted, locally verified product paths.
2. Real AI calls combined with deterministic safeguards.
3. Rule/heuristic systems presented with AI-oriented names.
4. Mounted demo APIs that store data only in Python dictionaries or return fixed values.
5. Dormant stubs, TODO workers, mocked connectors, and proposal capabilities that are absent.

The most important findings are:

- Several mounted APIs are unauthenticated.
- The generic database CRUD API allows unauthenticated table access and mutation.
- An unauthenticated users endpoint returns the `hashed_password` field.
- Mounted Lead, Customer, Conversation, Message, Integration, and Tool APIs contain process-memory stores that disappear on restart.
- `/api/v1/agents/{agent_id}/chat` returns a literal stub response instead of invoking an AI worker.
- Customer health scoring returns fixed values.
- A mounted lead scoring endpoint returns fixed values.
- Several analytics functions return only zeros.
- The voice filler is a hardcoded template selector, not AI-generated.
- The quick-assistant path contains hardcoded answers and can bypass RAG for selected queries.
- The six lead scores and revenue score are deterministic formulas with manually chosen weights, not trained models.
- The conversion probability is currently derived from the heuristic lead score, not learned from historical deals.
- BANT/MEDDIC normally use the local Qwen model, but fall back to keyword/evidence rules. There is no trained BANT artifact in the configured location.
- Lead document import says “AI extraction,” but its separate model-loader path points to a missing GGUF filename; it therefore falls back to heuristic extraction in the current workspace.
- Chat and fact extraction use the real local Qwen3-4B server.
- Dense document embeddings still use the Mistral cloud embedding API.
- ElevenLabs is the STT provider. TTS currently skips ElevenLabs and uses gTTS.
- The Tamil/Tanglish vocabulary is a manually curated subset, not a runtime read of all 1,511 PDF terms.
- `/status` is a hardcoded snapshot and already contains stale claims.
- The proposal’s React/Next.js, Temporal, ClickHouse, LightGBM, complete communications, industry packs, and Revenue Influence Score are not implemented.

This repository must not be exposed to an untrusted network until the P0 security items in this report are closed.

## 2. Verification evidence

Fresh checks on 24 July 2026:

- API and infrastructure health: healthy
- `/tenant`: HTTP 200
- `/user`: HTTP 200
- local llama.cpp server: `{"status":"ok"}`
- unified test suite: **332 passed, 261 warnings**
- test files using mocks/patches: **41 of 66**
- PostgreSQL tables: 102
- `lead_import_jobs`: present
- `conversation_analyses`: present
- `learning_signals`: present
- `qualification_frameworks`: absent
- `lead_qualifications`: absent
- `qualification_answers`: absent

The following routes returned HTTP 200 without authentication:

- `/api/database/tables`
- `/api/v1/tenants`
- `/api/v1/users`
- `/api/customers`
- `/api/leads`

The unauthenticated `/api/v1/users` response includes a `hashed_password` field. No password hash value was copied into this report.

Passing tests prove that tested behavior works. They do not prove that every mounted route is secure, durable, AI-driven, or connected to a real external provider.

## 3. Actual technology stack

### Application

| Layer | Actual implementation | Proposal comparison |
|---|---|---|
| Frontend | Static HTML, CSS, and JavaScript served by FastAPI | React/Next.js is not present; there is no `package.json` or Next configuration |
| Backend | Python, FastAPI 0.139.0, Uvicorn 0.51.0 | Matches Python/FastAPI |
| ORM/schema | SQLAlchemy 2.0.51, Alembic 1.18.5, Pydantic 2.13.4 | Real |
| Workflow/runtime | Kafka consumers and direct async calls | Temporal is absent |
| Primary relational store | PostgreSQL 15 | Matches proposal |
| Flexible memory | FerretDB 2.7 over DocumentDB/PostgreSQL | Additional architecture beyond proposal |
| Vector store | Qdrant | Matches proposal |
| Cache | Redis | Matches proposal |
| Object storage | MinIO/S3-compatible storage | Matches proposal |
| Event streaming | Kafka 7.5 with ZooKeeper | Real local infrastructure |
| Analytics database | None | ClickHouse is absent |

### AI and data processing

| Function | Actual stack | Current truth |
|---|---|---|
| Main answer generation | Qwen3-4B-Instruct-2507 Q4_K_M through llama.cpp OpenAI-compatible server | Real local model, 2.38 GB GGUF, server healthy |
| Dense embeddings | Mistral `mistral-embed` API | Real cloud API, not local |
| BM25 retrieval | PostgreSQL/`rank-bm25`-style lexical retrieval | Real deterministic retrieval |
| Document classification | Local Qwen attempt plus deterministic fallback | Hybrid |
| Business fact extraction | Local Qwen plus conservative regex/category drafts | Hybrid, human review required |
| Lead-file extraction | Separate `ModelManager` GGUF loader plus heuristic fallback | Configured GGUF filename is missing; current effective behavior is normally heuristic |
| BANT/MEDDIC | Local Qwen structured scoring; evidence/keyword fallback | Hybrid; no trained BANT artifact |
| Six lead scores | Python formulas and manually selected weights | Heuristic, not ML |
| Revenue score | Regex evidence point formula | Heuristic, not revenue prediction |
| Conversion probability | Derived from lead score | Not a trained conversion model |
| Sentiment | Small Naive Bayes model trained from 90 examples plus lexicon overrides | Real small ML model, but limited and rule-adjusted |
| Voice emotion | 64 KB CNN-MFCC checkpoint blended with prosody rules | Experimental; checkpoint history ends near 52% training accuracy and has no retained test evaluation |
| STT | ElevenLabs Scribe realtime/API | Real external service, quota/network dependent |
| TTS | gTTS `co.in` active; ElevenLabs code exists but is skipped | Real synthesis, not the intended premium streaming voice |
| Website parsing | aiohttp, BeautifulSoup, Playwright fallback | Real |
| Document parsing | pypdf, python-docx, python-pptx, openpyxl, OCR/Pytesseract | Real |
| ML libraries | PyTorch, scikit-learn | Used in limited areas |
| XGBoost | Code/dependency references | Not a proven current production model path |
| LightGBM | Absent | Proposal gap |

`requirements.txt` is mostly unpinned. The working virtual environment has exact installed versions, but a fresh installation could receive different package versions and behavior.

## 4. What is genuinely real

### 4.1 System 1 — business knowledge ingestion

Real implementation:

- multi-format upload
- PDF, DOCX, text, CSV, XLSX, PPT/PPTX, email, image, and scanned-PDF processing
- object-storage retention
- Kafka indexing jobs
- retries and a dead-letter state
- category selection and classification
- local-Qwen business fact extraction
- conservative deterministic extraction fallback
- human draft review/approval
- PostgreSQL canonical documents/chunks/facts
- Qdrant semantic chunks
- FerretDB document-memory projection
- SSRF-resistant, same-domain, robots-aware website crawler
- JavaScript rendering fallback with Playwright
- same-site PDF/DOCX/XLSX/CSV/PPTX/text/email asset download
- tenant UI processing and storage inspection

Hardcoded but appropriate:

- page, byte, timeout, extension, and same-domain limits
- category allowlists
- validation schemas
- approval rules

These are safety/product policies and should remain deterministic, although they should be moved to tenant/config settings where appropriate.

Limitations:

- maximum 25 pages
- 1 MB per page/asset and 5 MB total crawl
- only known downloadable extensions
- same exact hostname only
- client-rendered assets discovered only through parsed links
- external connected-source ingestion is incomplete or mock-tested

### 4.2 System 2 — knowledge and memory

Real implementation:

- PostgreSQL canonical structured facts
- PostgreSQL knowledge graph relations
- Qdrant semantic retrieval
- PostgreSQL/BM25 retrieval
- retrieval fusion and reranking
- FerretDB document, customer/lead, and conversation memory
- tenant filters
- approval filters
- citations
- conflict surfacing
- lead-context injection into the answer prompt
- user and assistant message persistence in the primary chat/nurture flow

Important clarification:

- PostgreSQL, FerretDB, and Qdrant do not store identical copies.
- PostgreSQL is the canonical structured store.
- FerretDB is flexible memory/raw projection.
- Qdrant is semantic evidence.

This separation is correct and is not dummy behavior.

### 4.3 Lead import and pre-nurturing persistence

Real implementation:

- durable import jobs and rows
- supported structured and document file parsers
- validation, normalization, deduplication, review, and commit
- PostgreSQL `Lead` creation
- FerretDB raw/full source-row memory
- URL discovery from committed lead data
- bounded authorized crawl
- crawled data sent through the normal indexing pipeline
- lead pre-nurturing state mirrored into PostgreSQL and FerretDB
- consolidated tenant lead detail surface

Critical AI truth:

- `LeadImportService._call_llm()` uses `ModelManager` with `GENERATOR_MODEL=qwen2.5-3b-instruct`.
- `LocalGGUFModelLoader` resolves that to `AI_MODELS/gguf/qwen2.5-3b-instruct-q4_k_m.gguf`.
- That file does not exist.
- The available model is `AI_MODELS/gguf/Qwen3-4B-Instruct-2507-Q4_K_M.gguf`.
- Therefore lead extraction/enrichment currently falls back to deterministic column mapping and rules unless this model path is repaired.

The import result can still be useful for CSV/XLSX because the heuristic mapper is extensive. It is misleading to call the current path fully AI-based, especially for unstructured PDFs, DOCX files, and images.

### 4.4 Main grounded chat

Real implementation:

- retrieves Qdrant and PostgreSQL evidence
- adds approved PostgreSQL facts and graph edges
- adds FerretDB lead memory
- calls the local Qwen server
- streams tokens
- requires evidence for company/product/deal claims
- persists the user question and AI answer
- provides citations and confidence metadata

Cloud dependency:

- the active hybrid retrieval path generates vectors with the Mistral embedding API.
- Local Qwen generates the answer, but the complete RAG path is not fully offline.

## 5. Hardcoded and heuristic AI behavior

Not all deterministic code is bad. Validation, routing, safety checks, and low-latency fallbacks often should be deterministic. The problem is when a formula, canned action, or in-memory response is presented as learned intelligence or completed automation.

### 5.1 Voice filler

File: `app/services/rag/filler_service.py`

Current behavior:

- keyword regex chooses one of `pricing`, `timeline`, `demo`, `technical`, `information`, or `general`
- response is selected from a hardcoded language/template dictionary
- a hash of the user text selects the template
- an in-memory dictionary avoids repeating the immediately previous choice
- state resets on process restart
- filler starts after a fixed 750 ms delay

Verdict: **hardcoded deterministic UX, not AI**.

It is not random dummy text; it is context-category aware. It is still too shallow for “perfect reply for every message.” It does not use retrieved lead context, conversation stage, emotion, or the generated answer plan.

There is also a latency risk: filler synthesis takes the speech lock. With gTTS, a slow filler can delay the real answer audio.

Recommended replacement:

- build filler intent from the already-running partial transcript classifier
- include worker role and conversation stage
- keep a curated safe phrase library
- pre-synthesize common phrases
- cancel queued filler audio when first answer audio is ready
- never use an LLM call only to produce the filler, because that adds latency

### 5.2 Quick assistant

File: `app/analysis/services/quick_assistant_service.py`

Hardcoded answers include:

- greeting
- assistant identity
- Vijay and Dhoni facts
- time/date
- AI/ML/RAG/Redis/Chroma explanations
- sentiment explanation
- a leave-letter template
- warm/hot lead messages based on sales keywords

The voice WebSocket invokes this before RAG when no worker is selected and the language is English. It persists the result with confidence `1.0` and `supported=True`, even though it did not retrieve evidence.

Verdict: **active canned-answer bypass**.

The `/user` page selects the SDR worker by default, so the default SDR flow bypasses the quick assistant. Selecting the generic Knowledge Assistant enables it.

Recommended action:

- remove person-specific trivia
- restrict the quick path to harmless greetings, acknowledgements, time/date, and commands
- do not mark canned factual answers as confidence 1.0/supported
- send sales/product questions through the worker/RAG path

### 5.3 BANT and MEDDIC

Real path:

- local Qwen scores BANT and MEDDIC components from transcript evidence
- JSON is parsed and validated
- evidence is accumulated in FerretDB

Fallback path:

- keyword/evidence heuristics generate component scores

Missing:

- no `AI_MODELS/bant` trained artifact
- no `qualification_frameworks`, `lead_qualifications`, or `qualification_answers` tables in the live schema
- the secondary relational BANT persistence path therefore cannot complete
- SPIN, CHAMP, ANUM, custom, and industry frameworks are not operational

Verdict: **real LLM-assisted analysis with heuristic fallback, not a trained BANT model**.

### 5.4 Six lead metrics

Files:

- `app/analysis/services/lead_intelligence_service.py`
- `app/analysis/services/lead_scoring_service.py`

ICP, intent, engagement, qualification, buying signal, relationship, and overall lead score use:

- keyword matching
- text length
- question count
- numeric evidence
- punctuation and uppercase ratios
- manually configured coefficients
- optional metadata/CRM values
- limited voice-emotion inputs

The coefficients are literal constants. Examples include fixed base scores, 0.35/0.25/0.20 score weights, and a fixed SDR qualification threshold of 40.

Verdict: **real deterministic scoring, not learned ML**.

The values should be labeled `heuristic_score` until calibrated against human outcomes.

### 5.5 Revenue score and conversion probability

`RevenueIntelligenceService` awards fixed points for:

- monetary expressions
- percentage expressions
- revenue/ROI/value terms
- urgency terms
- a structured CRM opportunity value

The “conversion probability” fallback effectively maps the lead score to a 3–98% range.

Verdict: **evidence counter and normalized heuristic, not a Revenue Probability Engine**.

No trained model currently learns from historical wins/losses, behavior, intent, qualification, industry, or deal velocity.

### 5.6 Sentiment

Current behavior:

- a small Naive Bayes model can be loaded/trained
- training data has 90 examples
- positive/negative/neutral word sets can override the model
- several phrase rules force a label to 0.82 probability
- unavailable-model fallback returns a fixed neutral distribution

Verdict: **small real ML model heavily corrected by rules**.

It is suitable for development signals, not a production multilingual sentiment claim.

### 5.7 Voice emotion

Current behavior:

- loads a small CNN-MFCC checkpoint
- blends CNN output 45% with acoustic/prosody rules 55%
- adds additional rule adjustments
- falls back completely to prosody rules if model loading fails

Checkpoint evidence:

- labels include `<mixed>`, `disagreement`, `negative`, `neutral`, `positive`
- retained history ends around 52.1% training accuracy
- no retained validation/test accuracy is present
- some checkpoint labels are discarded by the four-label blend

Verdict: **experimental hybrid, not production emotion recognition**.

### 5.8 Tanglish styling

File: `app/analysis/services/tanglish_style.py`

Current behavior:

- the source PDF is described as containing 1,511 English words
- the runtime does not load or search that PDF
- a manually curated subset is grouped into money, sales, time, technology, education, and business
- regex selects a topic subset
- the subset is inserted into the local Qwen prompt

Verdict: **hardcoded curated vocabulary used to condition a real LLM**.

This is not dummy, but it is not complete PDF-driven language adaptation. The source vocabulary should be converted to a versioned data asset and retrieved by topic.

## 6. Mounted dummy, unsafe, or non-durable APIs

### 6.1 Critical unauthenticated generic database API

Mounted from `app/main.py`:

- `app/routers/database_crud.py`

Capabilities:

- list every table
- inspect schemas
- read rows
- create rows
- update rows
- delete rows

There is no authentication, role check, table allowlist, or tenant filter.

Verdict: **critical security release blocker**.

Remove this router from the normal application immediately or protect it behind development-only configuration, admin authentication, strict table allowlisting, and tenant-aware authorization.

### 6.2 Unauthenticated tenant/user administration

Many `/api/v1` tenant/user/role/key routes do not depend on `_current_user`.

Observed:

- unauthenticated tenant listing
- unauthenticated user listing
- user records expose `hashed_password`
- unauthenticated tenant creation/update/delete
- unauthenticated user creation/update/deactivation
- unauthenticated role management
- API-key listing/revocation lacks consistent authentication

Password reset endpoints only return success messages and do not implement email/token/reset behavior.

Logout returns a message but does not revoke a token.

Verdict: **partly real database CRUD combined with dummy auth workflows and critical authorization gaps**.

### 6.3 Mounted in-memory lead/revenue API

File: `app/routers/leads.py`

All of these are process dictionaries:

- leads
- activities
- scores
- qualification frameworks
- qualifications
- opportunities
- proposals
- quotes
- meetings

Hardcoded behavior includes:

- recalculated lead score = 85
- normal minimum lead score = 50
- fixed score factors
- qualification score = number of answers × 25
- proposal “document ID” is only a new UUID

These records disappear on restart and are different from the real SQLAlchemy `Lead` records used by lead import and the tenant verification UI.

Verdict: **mounted demo API that conflicts conceptually with the real lead domain**.

### 6.4 Mounted in-memory Customer Intelligence API

File: `app/routers/customers.py`

All customer, contact, health, event, and renewal records are process dictionaries.

Hardcoded health score:

- 88 when force recalculation is requested
- otherwise at least 75
- fixed factor values
- fixed `trend="up"`

New customers receive:

- health score 0
- churn risk `unknown`
- expansion score 0

Verdict: **System 4 is currently a dummy API surface, not Customer Intelligence**.

### 6.5 Mounted in-memory conversations/messages

Files:

- `app/routers/conversation.py`
- `app/routers/message.py`

These maintain separate Python dictionaries for conversations, participants, messages, summaries, analysis objects, attachments, and reactions.

The real chat/voice memory path separately uses PostgreSQL models.

Verdict: **duplicate non-durable API surface**.

### 6.6 Mounted in-memory integrations

File: `app/routers/integrations.py`

Behavior:

- four integrations are hardcoded with fixed UUIDs and metadata
- creating a connection immediately returns `status="connected"`
- no OAuth exchange is performed
- sync creates a queued in-memory job
- no worker consumes that job
- webhook registration and events are in-memory

Verdict: **integration catalog/demo, not a real connection manager**.

### 6.7 Mounted agent chat stub

File: `app/routers/api_v1.py`

`POST /api/v1/agents/{agent_id}/chat` persists and returns:

`Stub response from {agent name}: {message}`

It returns:

- no citations
- confidence 0
- supported false
- latency 0
- token usage 0

Verdict: **explicit active stub**.

This route is separate from the working `/chat/` and `/ws/voice/...` paths.

### 6.8 Mounted in-memory tool API

File: `app/routers/tools.py`

Tool definitions, executions, permissions, and connector logs are process dictionaries. This is not the same as a real MCP provider action.

Verdict: **demo registry and execution ledger**.

## 7. AI worker truth

### SDR worker

Real:

- calls grounded chat
- calculates heuristic lead scores
- updates a durable PostgreSQL Lead
- records `ConversationAction`
- can hand off to Sales

Hardcoded:

- intent classification is substring matching
- meeting acknowledgement is canned
- threshold is fixed at 40
- “meeting booked” records an internal action but does not create a real calendar event

Verdict: **real conversation workflow with simulated external action**.

### Sales worker

Real:

- uses grounded chat for product context
- updates lead state
- records actions

Hardcoded/simulated:

- intent classification is phrase matching
- objection prefix is canned
- proposal acknowledgement is canned
- closing acknowledgement is canned
- proposal is a JSON dictionary, not a generated PDF/DOCX or delivered document
- “closing” phrases can mark a lead converted/closed-won without confirmation or human approval

Verdict: **partial worker; risky automatic stage changes and simulated proposal delivery**.

### Support worker

Real:

- grounded retrieval and citations
- confidence/conflict gates
- PostgreSQL conversation status
- FerretDB nurture mirror

Hardcoded:

- escalation/request/complaint intent is substring matching
- escalation acknowledgement is canned
- confidence threshold is fixed

Verdict: **substantially real local worker; external ticket assignment/delivery is absent**.

### Other workers

The orchestrator declares:

- customer success
- collections
- account manager
- executive

Only Support, SDR, and Sales are dispatchable.

Verdict: **the remaining four workers are not implemented**.

## 8. Communications truth

| Capability | Status | Hardcoded/dummy detail |
|---|---|---|
| Browser voice | Real locally | Browser WebSocket, AudioWorklet, VAD, barge-in, and WebAudio are implemented |
| STT | Real external | ElevenLabs dependency; no proven local fallback |
| TTS | Real fallback | gTTS is active because ElevenLabs TTS is explicitly skipped |
| Phone calls | Stub | Voice provider logs “would call”; no Twilio/Plivo telephone call |
| SMS domain dispatcher | Stub by default | `SmsProviderStub` logs what it would send |
| Push notifications | Stub | Firebase/APNs planned |
| Email webhook | Real local webhook | External outbound delivery depends on provider configuration |
| Gmail IMAP/SMTP | Provider-shaped implementation | Not equivalent to production certification |
| Brevo | Provider-shaped implementation | Must verify real delivery, receipts, retries, and tenant isolation |
| WhatsApp MCP | Includes mock-history fallback | Mock results must never be exposed as real conversation history |
| Slack MCP | Can enter fallback mock mode | Unit tests use mocked clients |
| CRM | Several adapters/interfaces | primary base client methods remain unimplemented; separate CRM router is not mounted |
| Campaign delivery | TODO | campaign worker `_process()` is empty |

There are multiple overlapping communications/integration implementations. A single provider abstraction and one durable outbox/delivery ledger should replace the competing stub, MCP, router, and worker paths.

## 9. Dormant or unfinished code

Explicit TODO/unfinished workers:

- `app/workers/ocr_worker.py`
- `app/workers/embedding_worker.py`
- `app/workers/crm_sync_worker.py`
- `app/workers/communication_worker.py`
- `app/workers/campaign_worker.py`
- `app/workers/analytics_worker.py`

These workers are not started by `start.bat`.

Important nuance:

- OCR and embedding are not wholly absent. The active indexing consumer performs parsing/OCR/indexing through `index_document()`.
- The placeholder OCR and embedding workers are dead/duplicate architecture and should be removed or completed.
- The startup script launches only API, indexing, knowledge sync, conversation analysis, and lead scoring.

Other unfinished/dummy code:

- streaming conversation pipeline raises `NotImplementedError`
- AI router contains TODO database, CRM, and agent execution
- MCP service can fall back to a stub
- voice-call and push providers are explicit stubs
- generic base model loader contains abstract `NotImplementedError` methods; those are acceptable only as true abstract interfaces

## 10. Frontend truth

### `/tenant`

This is a real static verification console, not a full React product frontend.

It calls real endpoints for:

- authentication
- knowledge upload
- knowledge processing status
- extraction review state
- three-store verification
- website ingestion
- lead-file upload
- import preview/commit
- lead URL crawling
- real PostgreSQL lead list/detail
- FerretDB and Qdrant lead evidence

It does not embed fake Sophia/Miller lead cards or the large product mockup shown in the earlier requirement.

### `/user`

This is a real static browser voice console.

It implements:

- login
- session creation
- worker selection
- realtime STT connection
- audio streaming
- typed turns
- assistant audio playback
- transcript bubbles
- worker results
- lead metrics
- BANT/MEDDIC
- latency cards

The displayed scores are real outputs from the backend, but “real” here means current heuristic/LLM hybrid outputs—not validated conversion predictions.

### `/status`

`app/static/status.html` is entirely hardcoded.

It contains fixed counts and manually written status claims. It is already stale:

- it says the local Qwen GGUF was never downloaded, but Qwen3-4B is present and the server is healthy
- it describes status from a previous session rather than querying current runtime state

Verdict: **documentation snapshot presented as a page, not a live dashboard**.

Replace it with a backend-generated capability registry or remove it from product navigation.

## 11. Analytics, learning, industry packs, and North Star

### Analytics

`app/routers/observability.py` includes routes that return literal zero metrics for conversations, leads, customers, agents, and the overall dashboard.

That router is not mounted by the current `app/main.py`, but the code is still dummy and should not be used as evidence of analytics completion.

`app/workers/analytics_worker.py` has an empty `_process()` method.

Verdict: **analytics is not implemented beyond health, retrieval logs, latency events, and a few operational records**.

### Learning system

`LearningSignal` model and migration exist.

There is no complete service that:

1. captures every worker action
2. matches the customer response
3. resolves the business outcome
4. measures performance
5. updates/retrains/calibrates a model
6. evaluates and safely deploys the update

Verdict: **schema scaffold only**.

### Industry adaptation

There is no industry-pack/plugin architecture or implemented Education, Healthcare, Real Estate, or Manufacturing pack.

Some prompts/keywords mention education and business terms, but that is not an industry pack.

Verdict: **absent**.

### Revenue Influence Score

The new conversation `revenue_score` is not the proposal’s Revenue Influence Score.

There is no cross-lifecycle attribution for revenue influenced through:

- Sales
- Support
- Renewals
- Collections
- Upsells

Verdict: **absent**.

## 12. Security and production hardcoding

Release-blocking concerns:

- wildcard CORS
- default application secret `change-me`
- default CRM encryption key
- literal local PostgreSQL username/password in Compose
- default object-storage credentials in settings
- webhook authentication can be disabled with an empty secret
- unauthenticated generic database CRUD
- unauthenticated tenant and user administration routes
- password hash included in user API output
- missing consistent tenant filtering across legacy/demo APIs
- integrations can report connected without authentication
- automatic closed-won state change from phrase matching
- no human approval for proposal/meeting/deal actions

Local defaults are acceptable for isolated development only. Startup should refuse unsafe defaults when `APP_ENV` is not `development`.

## 13. Appropriate hardcoding that should remain deterministic

These should not be replaced with AI:

- SSRF and public-address validation
- same-domain crawl enforcement
- robots.txt enforcement
- maximum payload/page limits
- file-extension allowlists
- tenant authorization rules
- schema validation
- PII/secret redaction keys
- retry counts and timeout defaults
- approval-state transitions
- duplicate detection identity rules
- database constraints
- rate limits
- confidence/action safety thresholds, once calibrated and configurable

AI should not make security, authorization, data-integrity, or legal-consent decisions.

## 14. Proposal capability classification

| Proposal area | Real | Heuristic/partial | Dummy/stub | Absent |
|---|---|---|---|---|
| System 1 | uploads, parsing, OCR, crawl, assets, storage, indexing, review | classification/extraction fallbacks | several connector mock modes | many live source connectors |
| System 2 | PostgreSQL/Qdrant/FerretDB, retrieval, graph, memory, citations | graph depth and production scale | none in core path | full production hardening |
| System 3 | local-Qwen BANT/MEDDIC, stored lead state | six metrics, revenue score, conversion estimate | mounted fixed-score lead API | SPIN/CHAMP/ANUM, calibrated probability model |
| System 4 | SQL models exist | limited fields | mounted in-memory customer API and fixed health score | real health/churn/expansion engines |
| System 5 | Support/SDR/Sales conversation paths | rule intents and simulated actions | agent-chat stub | four remaining workers |
| System 6 | learning table | interaction/action records | none | complete learning loop |
| Voice | browser streaming and external STT | gTTS, experimental emotion | telephone-call provider stub | production calling/receptionist |
| Email/WhatsApp/SMS | provider-shaped code | mocked/unverified integrations | SMS/voice/push stubs and mock history | certified end-to-end delivery |
| Analytics | some logs/latency | limited operational metrics | zero-return analytics code | proposal analytics |
| Industry packs | none | keyword mentions only | none | all packs |
| North Star | conversation evidence score only | none | none | revenue influence attribution |

## 15. Required remediation checkpoints

### P0 — security isolation

- unmount `/api/database`
- require authentication/authorization on every `/api/v1` management route
- remove `hashed_password` and other sensitive fields from responses
- enforce tenant scope centrally
- disable or remove in-memory demo routers from the normal app
- replace wildcard CORS
- reject unsafe default secrets outside development
- add authorization regression tests

Acceptance:

- unauthenticated requests receive 401/403
- cross-tenant requests receive 403/404
- no password/API secret/hash is returned
- no generic arbitrary-table mutation endpoint exists

### P1 — remove misleading duplicate APIs

- choose one PostgreSQL-backed Lead API
- choose one PostgreSQL-backed Conversation/Message API
- replace Customer dictionaries with repositories
- replace Integration dictionaries with durable connection models
- remove agent chat stub or route it through the real orchestrator
- remove or label `/status` as static documentation

Acceptance:

- data survives process restart
- UI and public API read the same records
- no route returns literal “Stub response”
- no fake connected/sent/booked status is emitted

### P2 — correct AI truth and model routing

- point lead-import extraction to the running Qwen3 server or the existing GGUF
- record `analysis_source` for every score: model, heuristic, fallback, or human
- rename heuristic conversion output
- add trained/evaluated conversion model only after sufficient labeled data
- create and migrate framework/qualification tables if relational persistence remains required
- validate voice-emotion checkpoint labels and publish test metrics
- convert Tanglish PDF vocabulary to a versioned data asset

Acceptance:

- lead-import logs show actual Qwen inference for unstructured documents
- every UI metric exposes its source/model version
- model accuracy is evaluated on held-out data
- fallback output is visibly labeled

### P3 — real actions and channels

- connect meeting action to a calendar provider
- generate a real proposal artifact and require approval before sending
- require confirmation before closed-won transitions
- implement a durable communications outbox
- connect and verify email, WhatsApp, SMS, and phone providers
- remove mock-history fallbacks from production configuration
- implement idempotency and provider receipt reconciliation

Acceptance:

- booked meetings exist in the provider calendar
- sent messages have provider message IDs and delivery status
- proposals can be downloaded and have approval/send audit records
- provider failure never returns a false success

### P4 — finish proposal systems

- Customer Intelligence
- Customer Success/Collections/Account Manager/Executive workers
- continuous learning
- database-backed analytics
- industry packs
- Revenue Influence Score
- production backup, restore, HA, security, load, and incident readiness

## 16. Final answer to the hardcoding question

Yes, there are substantial hardcoded and dummy sections.

The core knowledge/lead-memory/RAG/voice transport is real. The following are currently hardcoded or simulated and must not be presented as completed AI:

- fillers
- quick-assistant answers
- worker intent detection
- worker acknowledgements
- meeting/proposal/delivery actions
- six lead-score formulas
- revenue score
- conversion probability
- fixed lead/customer score endpoints
- customer health/churn/expansion surface
- agent chat route
- integration connection/sync surface
- analytics zero responses
- status page
- several communications and background workers

The immediate priority is not to replace every rule with AI. It is to:

1. secure and remove the misleading mounted demo APIs,
2. label heuristics truthfully,
3. route all duplicate surfaces to the real persisted implementation,
4. fix lead-import model routing,
5. connect worker actions to real providers,
6. evaluate models with proper datasets,
7. finish the missing proposal systems.

