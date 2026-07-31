# Follei next-chat handover

Prepared: 31 July 2026 (Asia/Kolkata)  
Repository: `Follei-backend-Team`  
Purpose: give a new Codex chat an accurate starting point without treating the product proposal as already implemented.

## 1. Product direction

The source proposal, `coirei follei base .pdf`, defines Follei as a **Computational Organization Platform**, not a chatbot or a simple workflow tool. Its intended core is the **Organizational Genome**: a living, executable model of a tenant's knowledge, people, policies, relationships, processes, decisions, and operational history.

The proposal adds two differentiators:

1. **Autonomous Policy Compiler** - converts SOPs, contracts, approvals, HR, compliance, and security documents into rules that govern agent actions.
2. **Decision Confidence Network (DCN)** - decides whether Follei can act, must ask for approval, or must collect more evidence based on organization-level evidence rather than an LLM's claimed confidence.

The practical product path today is smaller:

`tenant setup -> business knowledge ingestion -> lead import -> authorized URL enrichment -> PostgreSQL + FerretDB + Qdrant -> grounded chat/voice -> email/campaign/flow follow-up -> observable lead history`

## 2. Current architecture

```text
Static HTML UIs (/tenant, /tenant/flows, /tenant/activity, /user)
                         |
                    FastAPI (Python)
                         |
       +-----------------+------------------+
       |                 |                  |
 PostgreSQL          FerretDB             Qdrant
 canonical state     flexible memory      semantic evidence
       |                 |                  |
       +------ MinIO + Redis + Kafka -------+
                         |
                 Workers / local Qwen / providers
```

### Storage responsibilities

| Store | Intended ownership | Current use |
|---|---|---|
| PostgreSQL | Canonical transactional record | tenants, users, leads, import jobs, documents, facts, conversations, campaigns, flow versions/enrollments, outbox |
| FerretDB | Flexible evolving tenant/lead/customer/conversation memory | raw lead payloads, qualification/nurture context, crawled content and conversation projections |
| Qdrant | Tenant-filtered semantic evidence | indexed approved document and crawl chunks for RAG |
| MinIO | Original files / durable objects | uploads and reusable communication assets |
| Redis | cache and runtime coordination | cache/stream support |
| Kafka | background event transport | indexing, knowledge sync, analysis and related events |

Do not duplicate all data into all stores. PostgreSQL is the source of truth; FerretDB is flexible memory; Qdrant is retrieval evidence.

## 3. Repository map

| Path | Responsibility |
|---|---|
| `app/main.py` | FastAPI composition and mounted routers |
| `app/domains/lead_import/` | lead file parsing, validation, dedupe, commit, URL discovery and crawl hooks |
| `app/services/knowledge/` | parsing, extraction, memory projections, website ingestion and RAG support |
| `app/services/rag/` | hybrid retrieval, reranking, approval filtering, indexing and chat pipelines |
| `app/analysis/` | BANT/MEDDIC, lead scoring, sentiment/emotion and voice-related services |
| `app/services/communications/` | Gmail/Brevo/Twilio adapters, auto-reply, outbox, retries and attachment ingestion |
| `app/services/campaigns/` | campaign audience selection, persistence, outbox queueing and tracking model |
| `app/services/flows/` | editable nurturing graph, eligibility, enrollment and execution |
| `app/workers/` | indexing, sync, scoring, mail operations and flow execution workers |
| `app/static/` | static HTML/JS frontend; not React or Next.js |
| `alembic/versions/` | PostgreSQL migrations |
| `scripts/start_local_runtime.ps1` + `start.bat` | local Docker, migration, API and worker startup |

## 4. What is implemented and working locally

### Knowledge ingestion and System 1

- Upload and processing paths for PDF, DOCX, PPTX, spreadsheet, CSV, TXT, EML and supported images/scans.
- Object-storage source retention, durable indexing jobs, parsing/OCR, category-aware extraction, fact review/approval, PostgreSQL persistence, Qdrant indexing and FerretDB memory projection.
- Authorized, bounded same-domain website crawling with public-address checks, robots handling, byte/page limits, document-download discovery, and Playwright fallback for JavaScript pages.
- Tenant verification UI at `/tenant` for documents, imports, storage evidence and lead details.

### Lead ingestion and lead memory

- CSV/XLSX/PDF/DOCX/text/image lead import with preview, normalization, dedupe and durable `lead_import_jobs`.
- Structured fields are committed to PostgreSQL; full source-row payloads are retained in FerretDB; link discovery can run authorized web enrichment.
- Lead-detail API/UI combines structured records, import/crawl provenance, conversations, flexible memory and semantic evidence.

### Knowledge retrieval and AI conversation

- Tenant-aware hybrid retrieval (vector, lexical/hybrid support, reranking, approval filtering and citations).
- Main conversation paths store both user and assistant messages and project useful lead/conversation context to FerretDB.
- Local response generation is configured around Qwen3 through llama.cpp; Mistral embeddings remain configured for vector generation.
- Browser voice/chat architecture includes streaming-oriented components, VAD/barge-in concepts, phrase buffering, Tanglish prompt support and latency fields. Live quality still depends on model/provider availability.

### Revenue intelligence and workers

- BANT, MEDDIC, six lead metrics, evidence accumulation, lead scoring, SDR/Sales/Support worker paths and handoff behavior exist.
- These are mixed maturity: some use the local LLM, but several scores and thresholds remain deterministic heuristics rather than trained/calibrated models.

### Email, campaigns and flows

- Tenant-scoped Gmail connection records, Google OAuth, enable/disable controls, Gmail polling, SMTP replies, Brevo send support, inbound attachment ingestion, lead creation/matching and PostgreSQL/FerretDB conversation persistence are implemented.
- Mail operations worker runs Gmail polling, scheduled-campaign pickup, email outbox processing and retries.
- Campaign service selects audiences, applies consent/suppression checks, personalizes content, stores messages/conversations, creates outbox rows and supports scheduling. Attachments/images are supported through reusable communication assets.
- Flow Builder at `/tenant/flows` persists versioned graphs with immutable node IDs. It supports email, wait, score-branch, trigger, stop and task nodes.
- Flow enrollment is durable and visible in `/tenant` and `/tenant/activity`: each lead has an enrollment ID, current node, status, next run time and execution steps.
- The flow worker reconciles missing eligible leads, respects automatic-enrollment settings, prevents duplicate active enrollments across versions and stops flows on replies when configured.

### Startup and database state

- `start.bat` now discovers a project virtual environment or finds `py -3`/`python`, creates `.venv` when necessary, runs migrations, and starts required local services.
- Latest migration head: `20260731_flow_enrollment_control`.
- Latest local verification: startup completed, migrations applied, API and worker health checks passed, and 25 focused regression tests passed. This is not equivalent to a fresh full-suite production certification.

## 5. Proposal-to-code gap assessment

| Proposal layer | Status | Reality in this repository |
|---|---|---|
| Data connectors | Partial | document and lead ingestion are strong; Gmail is materially implemented; CRM/ERP/chat/telephony connectors exist but many have mocked or incomplete live paths |
| Data normalization | Partial | document and lead normalization exist; no single enterprise-wide canonical event schema |
| Knowledge extraction | Partial/strong | category-aware facts and entities work; coverage and evaluation are not enterprise-complete |
| Relationship discovery | Partial | entities/relations and knowledge graph pieces exist; broad cross-system organizational relationship discovery is not complete |
| Process mining | Not implemented | no durable event-log mining, bottleneck discovery, path discovery, or workflow learning engine |
| Policy compiler | Not implemented | policies can be ingested as knowledge, but they are not compiled into enforceable runtime rules or approval gates |
| Organizational Genome graph | Partial | documents, facts, entities and relations exist, but there is no unified executable tenant graph representing all organizational structure/process/policy state |
| Genome evolution | Partial | ingestion, sync/outbox and memory projections update knowledge; no governed continuous evolution pipeline or graph-version lifecycle |
| DCN / action confidence | Partial | retrieval confidence and validation signals exist; no independent organization-level confidence aggregation or autonomous-action policy |
| Workforce execution | Partial | SDR/Sales/Support paths exist; action completion with provider IDs and human approval gates is incomplete |
| Learning loop | Early | signals/models exist, but no closed, safe `action -> outcome -> evaluation -> model update` loop |

## 6. Important incomplete, heuristic or dummy areas

Do not describe the following as production complete:

- Global security: `app/main.py` still mounts broad legacy/demo surfaces including generic database CRUD, and CORS is wildcard. Authentication/tenant enforcement is inconsistent outside the newer canonical paths.
- CRM integrations: provider abstractions and OAuth routes exist, but base live operations deliberately raise `NotImplementedError` for several clients; sync worker remains TODO.
- WhatsApp: connector contains mock-history fallback and unfinished connection methods. It is not a working tenant QR onboarding product.
- SMS: Twilio/Brevo paths exist, but the general messaging dispatcher still includes `SmsProviderStub`; live delivery/consent/STOP/HELP/receipt certification is incomplete.
- Telephone: no production inbound/outbound calling or AI receptionist.
- Process mining, policy compilation and DCN: absent as product systems.
- Analytics: some metrics/instrumentation exist, but analytics worker is TODO and dashboard metrics are not production-audited.
- Campaign/communications: the new email path is functional locally, but provider lifecycle proof (delivery receipts, bounce/complaint, unsubscribe, quotas, outage/retry acceptance) is not complete. WhatsApp/SMS/voice campaigns remain incomplete.
- OCR and standalone embedding workers contain TODO bodies; the primary ingestion pipeline covers part of their role.
- `app/routers/api_v1.py` includes an explicit stub agent-chat response. It must not be confused with the grounded RAG/voice path.
- Predictive conversion/churn/renewal/expansion probabilities are not trained or calibrated. Label scores as **model**, **heuristic**, **fallback**, or **human-reviewed**.
- ElevenLabs availability/quota affects live STT/TTS. gTTS fallback is functional but slower and does not provide premium Tamil/Tanglish speech quality.

## 7. Current UI and operating flow

1. Register/login a tenant in `/tenant`.
2. Add/authorize a Gmail sender from the email connection controls if using email automation.
3. Upload business documents and inspect indexing/fact review.
4. Import leads; approve URL crawling only for URLs the tenant is authorized to collect.
5. Configure the default flow in `/tenant/flows`.
6. Activate the email flow only after a working Gmail sender is connected.
7. Either press **Start flow for leads** or enable automatic enrollment.
8. Inspect every enrollment, outbox item, message, inbound email and flow step in `/tenant/activity` and per-lead details in `/tenant`.

`/tenant/flows` is a real persistence/execution UI, but it is still an MVP editor rather than a complete drag-and-drop orchestration product. WhatsApp and phone actions are intentionally deferred.

## 8. Runbook for the next chat

Start with these commands from the repository root:

```powershell
.\start.bat --skip-browser
follei_backend\indic_tts_venv\Scripts\python.exe -m alembic current
follei_backend\indic_tts_venv\Scripts\python.exe -m pytest -q
```

If the canonical virtual environment does not exist, `start.bat` should discover `py -3` or `python` and create `.venv`; use `.venv\Scripts\python.exe` for direct commands in that case.

Before editing anything:

1. Run `git status --short`; this workspace may already contain user work and uncommitted implementation.
2. Confirm the migration head and live health endpoints.
3. Use an isolated test tenant for any flow/campaign action so no unintended customer email is sent.
4. Do not delete/reset unrelated changes.

## 9. Recommended delivery sequence

### P0 - security and repeatability

1. Protect or remove generic database CRUD and legacy/demo API surfaces.
2. Enforce authentication, tenant scope and RBAC across every tenant-owned resource.
3. Restrict CORS and eliminate development secrets/fallback credentials from production behavior.
4. Make a fresh clone start reproducibly and run the complete test suite.

Acceptance: unauthenticated and cross-tenant tests pass; a fresh developer can run the core journey without manual database repair.

### P1 - finish the present core product

1. Run a complete fresh-tenant acceptance: knowledge upload -> facts -> lead import -> crawl -> three-store evidence -> conversation -> flow email -> inbound reply -> stop flow.
2. Finish email provider operational proof: OAuth refresh/revoke, delivery/webhook receipts, bounce/complaint, suppression/unsubscribe, rate limits and outage recovery.
3. Complete campaign UI, schedule/time-zone behavior, recipient snapshots, frequency limits and audit history.
4. Add full tests for flow activation, delayed execution, reply stop, provider failure and tenant isolation.

Acceptance: one email-first sales nurture loop is secure, observable and durable end to end.

### P2 - build the real Organizational Genome foundation

1. Define a versioned tenant graph schema for people, teams, roles, customers, products, policies, processes, decisions, assets and external-system identifiers.
2. Define a normalized enterprise-event schema consumed by all connectors and workers.
3. Expand extraction into entity resolution and relationship confidence with provenance.
4. Build a graph projection service and a graph-change/outbox lifecycle.
5. Add process mining from CRM, email, task and flow events.

Acceptance: a tenant can inspect a versioned organizational graph with evidence and see it evolve from real events.

### P3 - policy compiler and DCN

1. Extract policy candidates from policy documents into reviewed rule objects.
2. Create a deterministic policy evaluation service before any consequential external action.
3. Add approval gates, audit logs, rule versions and rollback.
4. Build DCN from retrieval support, policy result, data freshness, actor permissions, workflow state and prior outcome signals.

Acceptance: Follei can explain why an action was allowed, blocked or escalated, with sources and policy version.

### P4 - workforce, channels, analytics and learning

1. Finish real provider-backed CRM/calendar/support actions with external IDs.
2. Add Customer Success, Collections, Account Manager and Executive Insights workers.
3. Complete WhatsApp only through an approved provider integration; do not rely on unmaintained mock/QR automation for production.
4. Replace heuristic-only revenue intelligence with labeled evaluation datasets and calibrated models.
5. Implement outcome collection, analytics, attribution and safe model-update governance.

## 10. Paste this to a new Codex chat

```text
Read FOLLEI_NEXT_CHAT_HANDOVER_2026-07-31.md first. Treat the Organizational Genome, Policy Compiler and Decision Confidence Network as the product target from coirei follei base .pdf, not as finished features. Start by checking git status, Alembic head, /health, and the full test suite. Preserve existing changes. Work in the recommended P0 -> P1 -> P2 order unless I explicitly reprioritize.
```

## Bottom line

Follei is a real multi-store, multi-tenant local prototype with strong ingestion, retrieval, lead memory, email-first nurturing and an observable flow execution layer. It is **not yet** the full Computational Organization Platform described in the PDF. The path to that product is: secure the current core, prove one complete email-first loop, then deliberately build the versioned organizational graph, policy compiler, process mining and DCN rather than presenting existing RAG and flow features as equivalents.
