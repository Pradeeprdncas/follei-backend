# INTERNAL REPORT

## Follei Platform Status

**Date:** July 24, 2026  
**Review Type:** Technical Implementation and Production-Readiness Review  
**Classification:** Internal

## Executive Summary

Follei has progressed from a conceptual autonomous workforce platform into a functional, multi-tenant backend with working knowledge ingestion, organizational memory, lead import, semantic retrieval, local AI generation, and browser-based voice interaction.

The platform’s strongest capabilities are the Business Intelligence and Knowledge systems. PostgreSQL, FerretDB, Qdrant, Redis, Kafka, and S3-compatible object storage are integrated into the local runtime. Documents and authorized websites can be processed into structured facts, semantic evidence, and flexible memory.

Revenue Intelligence and AI Workforce capabilities are operational at an early-to-middle maturity level. BANT, MEDDIC, six lead metrics, lead memory, SDR, Sales, and Support workflows execute locally. However, several scores remain heuristic rather than statistically calibrated predictive models, and several worker actions are internal records rather than completed external actions.

Communications require careful status wording. Email and SMS contain meaningful provider implementations, but they have not met the acceptance criteria for a fully complete production channel. Campaign execution is not complete.

### Current progress

| Measurement | Status |
|---|---:|
| Core local MVP implementation | 70–75% |
| Full Version 1.0 proposal maturity | Approximately 38% |
| Production readiness | Approximately 30–35% |
| Unified automated suite | 332 passed |
| Current infrastructure health | Healthy |

The earlier single figure of 67% is reasonable only as a simplified description of the core product implementation. It should not be used to describe the complete Version 1.0 proposal or production readiness.

### Overall conclusion

Follei has a substantial technical foundation, but it is not yet market-ready. The immediate priorities are security isolation, replacement of mounted in-memory/demo APIs, completion of real communication delivery loops, and truthful labeling of model, heuristic, and fallback outputs.

**Page 1**

---

## Development Status by System

| System | Current status | Capability assessment |
|---|---:|---|
| Business Intelligence | 75–80% | Multi-format ingestion, OCR, website crawling, downloadable document discovery, category-aware extraction, storage, and review are working. Production source connectors remain incomplete. |
| Knowledge System | 80–90% | PostgreSQL, FerretDB, Qdrant, hybrid retrieval, citations, memory, approval filtering, and lead-context injection are the strongest areas. Production hardening and broader graph validation remain. |
| Revenue Intelligence | 40–50% | BANT, MEDDIC, six metrics, revenue evidence scoring, and persistence work. Conversion probability is heuristic and not trained on historical outcomes. |
| Customer Intelligence | 15–20% | Models and schemas exist, but mounted customer health behavior is in-memory and fixed. Churn, adoption, satisfaction, renewal, and expansion engines are incomplete. |
| AI Workforce | 30–35% | SDR, Sales, and Support are dispatchable. Customer Success, Collections, Account Manager, and Executive Insights are not implemented. Several actions remain simulated. |
| Learning System | 10–15% | A learning-signal schema exists. There is no complete action-to-outcome-to-model-update loop. |
| Communications | 35–45% | Browser voice and local chat are functional. Email and SMS provider code exists but is not fully production-certified. Phone, campaigns, and unified delivery operations are incomplete. |
| Analytics | 10–15% | Health and latency information exists. Proposal-level revenue, customer, and operational analytics are largely absent or return placeholder values. |
| Industry Packs | 0–5% | No Education, Healthcare, Real Estate, or Manufacturing pack architecture has been completed. |
| Revenue Influence Score | 0–5% | Conversation revenue evidence exists, but cross-lifecycle revenue attribution is not implemented. |

## Strongest Completed Areas

- PostgreSQL canonical business and lead data
- FerretDB flexible document, lead, and conversation memory
- Qdrant semantic evidence
- Redis caching and runtime support
- Kafka indexing and synchronization
- MinIO/S3-compatible source retention
- PDF, DOCX, TXT, CSV, XLSX, PPTX, email, image, and OCR ingestion
- authorized website crawling
- website PDF/document discovery
- human knowledge review and approval
- grounded RAG generation
- local Qwen3-4B answer generation
- lead-file preview and commit
- lead URL crawling and pre-nurturing state
- tenant lead and storage inspection
- browser microphone streaming
- realtime STT integration
- VAD and barge-in
- streamed token-to-phrase TTS pipeline
- user and AI response persistence
- SDR, Sales, and Support local dispatch

**Page 2**

---

## Communication Channel Status

### Email

**Current classification: Substantially implemented, not fully production-complete**

Implemented:

- inbound email-shaped Support webhook
- tenant-aware grounded response generation
- webhook secret support
- Gmail IMAP mailbox polling
- Gmail SMTP reply delivery
- bounce, self-send, list, and auto-reply loop protection
- tenant resolution
- Brevo transactional email provider
- Brevo inbound auto-reply workflow
- confidence threshold and rate-limit configuration
- email provider adapter and health reporting
- Gmail and Outlook MCP connector implementations
- automated tests for inbound routing and Gmail/Brevo behavior

Not yet sufficient for “fully complete”:

- Gmail/Outlook connector tests primarily use mocked network calls
- Gmail auto-reply worker is not started by the standard `start.bat`
- no retained production delivery-rate evidence
- no retained bounce/complaint/provider-receipt reconciliation report
- no full multi-tenant OAuth lifecycle certification
- no production campaign-to-email delivery loop
- no completed communications outbox guaranteeing idempotent retries
- no load, failover, or provider outage test

**Certification status: Not signed off as fully complete**

Email may be called fully complete only after real-provider delivery, receipt reconciliation, retries, worker startup, tenant isolation, and operational monitoring are demonstrated.

### SMS

**Current classification: Provider implementation exists, not fully production-complete**

Implemented:

- Twilio SMS client
- Twilio webhook validation code
- Twilio auto-reply orchestration
- Brevo transactional SMS provider
- provider selection through `SMS_PROVIDER`
- phone-number normalization
- provider health checks
- automated provider-routing and request tests

Not yet sufficient for “fully complete”:

- active settings default to Twilio, but Twilio account credentials are not configured
- Brevo provider tests mock the HTTP transport
- the legacy messaging dispatcher still contains `SmsProviderStub`
- the standard communication worker has an empty execution method
- no retained live carrier delivery receipt
- no STOP/HELP/consent/compliance workflow
- no durable retry/outbox reconciliation
- no production failure and rate-limit test

**Certification status: Not signed off as fully complete**

SMS may be called fully complete only after a selected provider is live, real messages and receipts are verified, compliance controls are implemented, and stub paths are removed from production routing.

### Campaigns

**Current classification: Not complete**

Present:

- campaign event definition
- campaign scheduler-related code
- domain directory
- Kafka-oriented campaign worker shell

Missing:

- campaign worker `_process()` implementation
- complete campaign CRUD and launch API
- recipient segmentation
- audience snapshotting
- message personalization
- scheduling and timezone delivery rules
- consent and suppression lists
- frequency caps
- channel orchestration
- delivery, bounce, open, click, reply, conversion, and unsubscribe tracking
- retry and dead-letter processing
- campaign analytics
- production frontend workflow

The current campaign worker explicitly contains:

`pass  # TODO: Implement campaign execution`

**Certification status: Incomplete**

Campaigns cannot currently be described as fully complete.

### Voice

**Current classification: Functional browser voice pipeline; telephone channel incomplete**

Implemented:

- browser audio streaming
- realtime STT
- partial and committed transcript events
- voice-activity detection
- barge-in
- local Qwen streaming generation
- phrase buffering
- TTS playback
- Tanglish prompting
- latency telemetry

Limitations:

- current TTS skips ElevenLabs and uses gTTS
- telephone inbound/outbound provider is still a stub
- AI receptionist is not implemented
- voice-emotion model remains experimental
- no formal p50/p95 benchmark and production call-quality report

**Page 3**

---

## Real Intelligence Versus Heuristic Behavior

### Real AI/model usage

- Qwen3-4B local answer generation
- Qwen-assisted business fact extraction
- Qwen-assisted BANT and MEDDIC analysis
- Mistral cloud embeddings
- ElevenLabs STT
- small Naive Bayes sentiment model
- CNN-MFCC voice-emotion checkpoint

### Heuristic or hardcoded behavior

- filler selection and filler text
- quick-assistant canned answers
- SDR, Sales, and Support intent classification
- worker acknowledgement messages
- six lead metric weights
- revenue evidence score
- conversion probability fallback
- SDR qualification threshold
- Tanglish topic vocabulary subset
- customer health score endpoint
- legacy lead score endpoint

Heuristics are not automatically defects. They are appropriate for validation, security, routing, and low-latency fallback. They become a product risk when presented as trained prediction or completed autonomous action.

### Current worker action truth

| Action | Current behavior | Required production behavior |
|---|---|---|
| Meeting booking | Stores a `meeting_booked` conversation action | Create a real calendar event and retain provider ID |
| Proposal generation | Stores a structured JSON proposal summary | Generate downloadable proposal, obtain approval, deliver it |
| Deal closing | Phrase matching can set lead to converted | Require confirmation/approval and synchronize the CRM |
| Support escalation | Changes local PostgreSQL conversation state | Assign or create a real support ticket |
| Email send | Provider implementations exist | Prove delivery and reconcile provider events |
| SMS send | Provider implementations exist | Prove carrier delivery and consent compliance |
| Campaign launch | Worker shell only | Execute recipients, channels, retries, tracking, and reporting |

## Security Status

**Classification: Critical remediation required**

Verified release blockers:

- generic database CRUD is mounted without authentication
- tenant and user administration routes lack consistent authorization
- the users response includes `hashed_password`
- several mounted APIs have no tenant enforcement
- wildcard CORS is enabled
- unsafe development-secret defaults exist
- mounted in-memory integration APIs can claim `connected` without OAuth

Follei must not be exposed to an untrusted network in this state.

**Page 4**

---

## Priority Remediation Checkpoints

### P0 — Security isolation

- unmount `/api/database`
- enforce global authentication and authorization
- enforce tenant scoping on every API
- remove password hashes, secrets, and internal credentials from responses
- restrict CORS
- reject unsafe default secrets outside development
- add cross-tenant and unauthenticated regression tests

### P1 — Replace mounted demo and duplicate domains

- replace in-memory Lead API with PostgreSQL repositories
- replace in-memory Customer API with PostgreSQL repositories
- replace in-memory Conversation and Message APIs
- replace in-memory Integration and Tool APIs
- remove the stub agent chat route
- make UI and API consume the same canonical domain services

### P2 — Complete intelligence routing

- route lead document extraction through the running Qwen3 model
- expose the analysis source for every score
- label outputs as model, heuristic, fallback, or human-reviewed
- implement calibrated conversion prediction
- validate sentiment and emotion on held-out multilingual datasets
- add SPIN, CHAMP, ANUM, and tenant-defined frameworks

### P3 — Certify Email and SMS

- choose the production email and SMS providers
- start required workers through the standard runtime
- remove stub fallbacks from production configuration
- implement durable outbox and idempotency keys
- verify live send and receive
- store provider IDs and delivery receipts
- implement retry, rate limit, bounce, complaint, consent, and suppression handling
- run tenant-isolation and provider-outage tests

### P4 — Build Campaigns

- campaign CRUD and launch controls
- segment and recipient snapshotting
- template and personalization engine
- channel selection
- scheduler and timezone rules
- consent, suppression, unsubscribe, and frequency controls
- campaign worker execution
- retries and dead-letter processing
- delivery and engagement event ingestion
- campaign analytics and frontend

### P5 — Complete autonomous actions

- calendar integration
- proposal document generation
- human approval gates
- CRM deal synchronization
- support ticket creation
- Customer Success, Collections, Account Manager, and Executive workers

### P6 — Production readiness

- backup and restore drills
- high availability and failover
- load and soak testing
- security assessment
- monitoring, paging, runbooks, and SLOs
- incident and rollback exercises

## Completion Sign-Off Rules

The following wording can be used only after the corresponding acceptance evidence exists:

| Statement | Required sign-off evidence |
|---|---|
| “Email is fully complete” | Live inbound/outbound provider proof, delivery/bounce reconciliation, retry/outbox, worker startup, tenant isolation, monitoring |
| “SMS is fully complete” | Live carrier proof, receipts, compliance, retry/outbox, stub removal, monitoring |
| “Campaigns are fully complete” | Full launch-to-recipient execution, scheduling, consent, delivery tracking, analytics, frontend, failure recovery |

Until those gates pass, the approved wording is:

- **Email: substantially implemented; production certification pending**
- **SMS: provider implementation available; production certification pending**
- **Campaigns: incomplete**

## Conclusion

Follei’s foundation is meaningful and technically capable. The platform already builds organizational memory, retrieves tenant-aware knowledge, imports and enriches leads, supports pre-nurturing, and runs local AI-assisted conversations.

The remaining work is not cosmetic. Security isolation, durable canonical APIs, real communication delivery, campaign execution, calibrated intelligence, and operational hardening are required before Follei can be described as a production-grade autonomous workforce platform.

The fastest credible path to market readiness is:

1. close P0 security,
2. eliminate mounted demo APIs,
3. certify Email and SMS,
4. implement Campaign execution,
5. connect worker actions to real providers,
6. complete production hardening.

**Page 5**
