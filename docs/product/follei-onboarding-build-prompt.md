# Follei — Onboarding Rebuild: Engineering Brief

Use this as the starting prompt for a coding agent (Claude Code / Codex) or as a spec to hand an engineer. It consolidates every decision made so far — repo setup, stack, data model, and the full onboarding flow — into one actionable brief.

---

## 0. Mission

We are rebuilding Follei's onboarding flow from scratch on a fresh `main` branch, while preserving the existing codebase as a reference. This is Phase 1 only — registration through flow-builder handoff. Do not build CRM integration, lead-nurturing logic, or lead scoring in this phase; those are explicitly out of scope (see Section 7).

## 1. Repo setup — do this first

1. From the current state of the repo, create and push a branch: `git checkout -b old-follei` — this preserves the existing work (the `tts-with-bant-` merge, the ~143-table schema, the six-system product build) as a pullable reference, not something we build on top of directly.
2. On `main`, start clean.
3. Create `/docs/product/` and commit the source documents into it as versioned artifacts:
   - `Follei_Product_Design.pdf` (Organizational Genome, Autonomous Policy Compiler, Decision Confidence Network)
   - `Follei_Autonomous_Business_Workforce_Platform.pdf` (six-system architecture, tech stack, industry packs)
   - Onboarding UI reference screenshots (the SaaSFlow-style flow: Google Workspace connect screen listing Gmail/Contacts/Calendar/Drive, step-by-step workspace setup)
4. This `/docs/product/` folder is the single source of truth the team points to — not scattered notes.

## 2. Stack — current phase (cloud models, single VPS)

No local model hosting yet. This significantly simplifies infra for now.

| Layer | Choice |
|---|---|
| API | FastAPI, fully async |
| Canonical DB | PostgreSQL |
| Flexible memory | FerretDB |
| Vector store | Qdrant (single collection, tenant_id as a filtered payload field — not collection-per-tenant) |
| Cache / async jobs | Redis + Redis Streams (consumer groups per worker type) |
| Object storage | MinIO |
| Embeddings | Mistral API (cloud) |
| Generation | Hosted LLM API (OpenAI or Claude — TBD), "basic" tier for now |
| Infra | 1 VPS (16 vCPU / 64GB recommended) — everything above except the two cloud model APIs |

Storage ownership rule: **Postgres owns anything transactional or audited** (tenant state, approvals, contact records, lead verification results, workflow versions). **FerretDB owns flexible/high-volume data** (knowledge digest, ingestion metadata, memory). **Qdrant only ever holds vectors + minimal filtering payload.**

## 3. Project structure

```
follei-backend/
├── app/
│   ├── core/                # config, security, db session, settings
│   ├── db/
│   │   ├── base.py          # shared declarative Base
│   │   └── session.py
│   ├── models/               # SQLAlchemy, split by domain
│   │   ├── tenant.py          # Tenant, User, ChannelConnection
│   │   ├── knowledge.py       # KnowledgeSource, Document, Chunk (metadata only)
│   │   ├── lead.py            # Lead, LeadVerification
│   │   ├── workflow.py        # WorkflowDefinition, WorkflowNode, WorkflowVersion, ApprovalState
│   │   ├── integration.py     # GoogleWorkspaceConnection, WebsiteConnector, GoogleSyncState
│   │   └── campaign.py        # Campaign, CampaignAsset
│   ├── schemas/               # Pydantic, mirrors models/
│   ├── routers/                # FastAPI routers, mirrors models/, versioned under /api/v1
│   ├── services/                # business logic, one file per domain
│   │   ├── onboarding_service.py
│   │   ├── google_workspace_service.py
│   │   ├── ingestion_service.py
│   │   ├── website_connector_service.py
│   │   ├── llm_service.py        # thin adapter over the hosted LLM API
│   │   ├── embedding_service.py  # thin adapter over Mistral
│   │   └── workflow_service.py
│   ├── integrations/             # thin external-API adapters, no business logic
│   │   ├── google/                # oauth.py, gmail.py, drive.py, calendar.py, contacts.py
│   │   └── website_scraper/
│   ├── workers/                   # Redis Streams consumers
│   │   ├── tenant_provisioning.py
│   │   ├── knowledge_ingestion.py
│   │   └── website_scrape_scheduler.py
│   └── main.py
├── alembic/
├── tests/
└── docs/product/
```

Routers stay thin (validate → call service → return). Services hold decision logic. Integrations are pure adapters with no business rules. `crm/` integration folder is intentionally absent — CRM is out of scope for this phase.

## 4. Onboarding flow — build in this order

### 4.1 Registration
- Fields: name, company name, mobile no, email. Auth via Google sign-up or mobile OTP, then a business-contact-details form.
- On submit: create `tenants` row (Postgres, status `pending_setup`) and `users` row.
- Publish `tenant.created` to a Redis Stream. A worker consumes it and:
  - Provisions the tenant's Qdrant payload namespace (no new collection).
  - Initializes the tenant's FerretDB namespace.
  - Seeds a placeholder workflow skeleton (replaced in 4.6).
- Frontend does not block on this — proceeds immediately to industry selection.

### 4.2 Industry + company type (mandatory, step 2, before any upload)
- `PATCH /api/v1/tenants/{id}` writes `industry` (enum) and `company_type` (`b2b` / `b2c`) to the tenant row.
- Enforce server-side: no `industry` set → block progression to knowledge upload.
- `company_type` isn't used yet in this phase — it's captured here because Phase 2's flow-skeleton generator will need it (B2B skews mail-first, B2C skews WhatsApp/call-first).

### 4.3 Channel setup — two different implementation classes

**Email (build first — lowest friction):**
- Google OAuth at login requests Gmail (read + send), Drive (read), Calendar (read), Contacts (read) scopes together — avoid a second consent round-trip.
- Cap OAuth'd Gmail to transactional/1:1 reply-threaded mail only. Do not route bulk send through it — Gmail flags volume sending as spam/promotions regardless of any per-day cap.
- For campaign-volume sending: separate ESP integration (SendGrid/Brevo/Postmark) on a dedicated sending domain with SPF/DKIM/DMARC — a tenant-level config, stored on the tenant record (ESP credentials + verified-domain status).
- Known gaps to close before calling this "done": durable delivery receipts, bounce/retry handling, OAuth token refresh/expiry, outage behavior.

**Phone / WhatsApp / SMS (provider-gated — build second):**
- Each needs an external paid provider account (Twilio for voice/SMS, WhatsApp Business API) with provider-side approval. Entering a number only triggers a provisioning workflow, not an instant connection.
- `channel_connections` table (Postgres): `provider`, `status` (`pending`/`approved`/`active`/`failed`), provider account reference, per tenant.
- Enforce: onboarding cannot reach "complete" unless at least one channel beyond email is `active`.

### 4.4 Knowledge ingestion pipeline
- User uploads docs, or connects Google Workspace (using the OAuth already granted), or adds a website URL.
- **Google Workspace sync** (mirror the reference UI's "connecting Gmail / Contacts / Calendar / Drive" checklist):
  - Initial full sync on connect: Drive file listing, Gmail message metadata, Contacts, Calendar → write raw references to `google_sync_state` (resource type, last sync token, status) in Postgres, queue content into ingestion.
  - Ongoing sync via Drive `changes.list` and Gmail `history.list` — incremental, not a one-time pull. Push notifications via Google Cloud Pub/Sub if near-real-time is wanted later; polling is fine to start.
- **Website connector**: `WebsiteConnector` model (`tenant_id`, `url`, `crawl_frequency`, `last_crawled_at`, `content_hash`). A scheduled worker crawls periodically, diffs against `content_hash`, only pushes changed pages into ingestion. Respect `robots.txt`, rate-limit per domain. Non-blocking — onboarding only captures the URL and kicks off the first crawl.
- **Ingestion mechanics**: files → MinIO → async worker does semantic + layout-aware chunking → batch chunks and call Mistral embeddings (don't call per-chunk) → dual write: vectors + tenant_id payload → Qdrant; chunk text + metadata → FerretDB.
- **AI classification pass**: sorts ingested content into categories (products, pricing, policies, FAQs, competitors, sales/support/payment process), **scoped by the tenant's `industry`**.
- **Overview screen**: read-only view over the FerretDB digest, showing what was ingested by category.
- Gate: at least one connected knowledge source or tool (e.g. Gmail) required before this step is complete.
- Publish ingestion work to `stream:ingestion.pipeline`; worker consumes with retry/backoff on Mistral rate limits, logs per-chunk failures rather than failing the whole batch silently.

### 4.5 Lead CSV import + validation
- Backend validation, synchronous, before accepting the batch:
  - Row count ≥ 50, or reject with a clear count-short error.
  - Each row needs ≥ 2 contactable methods (phone and/or email) — reject that row (decide: partial-accept the rest of the batch, or reject the whole batch — pick one and be consistent) if it falls short.
  - Optional `link` column (company/LinkedIn/profile URL) — validated as well-formed URL, not scraped. (Scraping is Phase 2.)
- Store validated leads in Postgres with a `verification_status` field; log failed rows with a reason.
- No scraping, scoring, or flow logic here — onboarding only validates structure.

### 4.6 Flow-skeleton generation + handoff
- Trigger: knowledge ingestion + lead import both complete.
- Generate an initial node-tree workflow (not a flat list) seeded from the tenant's `industry` + `company_type`, using the industry pack's default topology.
- Write the workflow definition, version, and approval state to **Postgres** as canonical, auditable state.
- Hand off to the flow builder UI: user verifies/edits, then hits start. "Start" flips the tenant to `active` — this is the actual onboarding-complete signal.

## 5. API structure

Layered, thin routers, `/api/v1/` versioned from day one:

```
routers/       → validate input, call one service method, return
services/      → business logic
repositories/  → DB access, one per model, hides SQLAlchemy from services
models/        → SQLAlchemy, split by domain (Section 3)
```

Every AI-dependent endpoint streams its response (SSE or chunked HTTP) rather than waiting for full generation — cloud LLM calls are a network round-trip we don't control, so perceived latency depends on getting the first token back fast, not full completion time. Anything non-critical to the immediate response (logging, analytics, follow-up actions) goes onto a Redis Stream, not inline.

## 6. Redis Streams — event list for this phase

| Stream | Published by | Consumed by |
|---|---|---|
| `stream:tenant.created` | Registration endpoint | `workers/tenant_provisioning.py` |
| `stream:ingestion.pipeline` | Upload / Google sync / website crawl | `workers/knowledge_ingestion.py` |
| `stream:website.crawl` | Scheduler (cron/beat) | `workers/website_scrape_scheduler.py` |
| `stream:workflow.generate` | Ingestion + lead import both complete | Flow-skeleton generator |

Use consumer groups (`XREADGROUP`) per worker type for horizontal scaling. Enable Redis AOF persistence so stream entries survive a restart.

## 7. Explicitly out of scope for this phase

- **CRM connection** — post-onboarding, not in this flow. No CRM router, service, or table beyond the empty stub folder.
- **Universal CRM scraper / Zapier-style connector** — not a real shortcut (Zapier's breadth is hundreds of hand-built per-CRM OAuth apps, not a trick). If prioritized later, evaluate a unified-API vendor (Merge.dev / Apideck / Nango) instead of hand-rolling.
- **First-touch logic, outcome tracking, hot/warm/cold/frozen lead scoring** — Phase 2 (System 3, Revenue Intelligence). Onboarding only collects the inputs (`company_type`, validated leads, connected channels) that Phase 2 will consume.
- **Campaign module** (image/text/prompt mail generation) — separate, non-blocking feature, after the core loop works.
- **Local model hosting** — deferred; cloud APIs only this phase (Section 2).

## 8. Acceptance criteria for "Phase 1 done"

- A new tenant can go: register → select industry + company type → connect Google Workspace → connect at least one non-email channel → upload or connect a knowledge source → see an ingestion overview → upload a valid 50+ lead CSV → land in the flow builder with a generated, editable workflow → hit start and reach `active` status.
- Every AI-dependent step (classification, flow-skeleton generation) is scoped by the tenant's `industry`, not a flat universal template.
- No step silently allows progression past a gate (industry selection, ≥1 non-email channel, ≥1 knowledge source, valid lead CSV) without the backend enforcing it — not just the frontend.