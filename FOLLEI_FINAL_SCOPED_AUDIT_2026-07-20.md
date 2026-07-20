# Follei final scoped audit — Systems 1 and 2

Final audit date: 2026-07-20 (Asia/Kolkata)

This is the authorized Phase 8 recomputation. It uses the same strict 0–4 rubric as `FOLLEI_FULL_PROPOSAL_AUDIT_2026-07-20.md`:

- 0 absent
- 1 code only
- 2 passing automated proof
- 3 fresh/retained live service proof
- 4 production hardening proof

The user's current scope explicitly excludes Google Drive, OneDrive, SharePoint, Notion, Confluence, Gmail, Outlook, WhatsApp, Teams, Slack, CRM, ERP, LMS, accounting-software, and ticketing-platform connectors. Those rows remain in the full-proposal score but are excluded from the user-scoped System 1–2 score.

No row receives status 4: there is still no production backup/restore drill, HA/failover proof, long load/soak result, formal security review, or operational alert-response record.

## Final evidence catalog

| ID | Literal result |
|---|---|
| F1 | Required tenant `87e38dbc-0218-4cd1-be7e-7d55721b2a07`: authenticated `POST /chat/` asking “What is the refund window?” returned HTTP 200, `45 days`, `supported:true`, and non-empty citations after approval-consistency repair. |
| F2 | Fresh Kafka/live-store rows were created for Brochure, Product Catalog, SOP, Competitor, Customer Segment, Payment Process, approved Product, approved Service, dedicated SLA, Call Transcript, Knowledge Article, and Product→Feature. Every row has retained job/document/draft/operational/chunk IDs in the continuation evidence. |
| F3 | Live graph chain and chat citations passed for Feature→Benefit, Benefit→Customer Segment, Customer Segment→Objection, and Objection→Response. The approved source draft is `2ed5d213...`; every query returned `supported:true` and an exact `graph_relation` citation. |
| F4 | One unified command, `python -m pytest -q`, collected the main, MCP, and AI directories and returned **273 passed, 0 failed, 216 warnings in 30.40s**. |
| F5 | Fresh Kafka upload job `e3dc26f0-1367-471d-b5c9-034c356be135` produced document `56360108-d3d7-4638-8a47-0e9ddc701857`, status `indexed`, disposition `new`, attempt `1`. |
| F6 | Three-store read for that exact tenant/document: PostgreSQL had the indexed canonical document and one chunk; Qdrant had point `4f7bfbc5-ede2-4d00-8aec-89f70f81a8b4`; FerretDB had `projection_type:indexed_document_summary`. Outbox event `67e54d2b-858b-4b9c-b5cc-7971854bfe6a` completed deliveries `postgres:completed, ferret:completed`. |
| F6b | Historical projection backfill scanned 27 indexed documents and processed 26 new sync events. Cross-store comparison then returned `indexed_documents:27`, `ferretdb_document_projections:27`, `missing:[]`. Duplicate uploads now idempotently enqueue a missing projection without re-embedding. |
| F7 | Final retrieval question about the Knowledge Recovery Runbook returned the correct three roles, `supported:true`, confidence `0.7`, and only two relevant citations: exact `qdrant_chunk` plus exact `ferretdb_document_memory`, both for `phase8-three-store-proof.txt`. |
| F8 | Final health: API, PostgreSQL, Redis, Qdrant, Kafka, FerretDB, and object storage are `ok`; indexing and knowledge-sync active queues are zero. One deliberately retained dead-letter test record remains. |
| F9 | External System 3/5 repository audit: `51 passed, 3 failed`; isolated API start failed on missing `chromadb`; no tenant isolation, translation artifact, SDR worker, or Sales Executive worker. See `FOLLEI_EXTERNAL_SYSTEM3_SYSTEM5_AUDIT_2026-07-20.md`. |

## Store responsibilities and upload guarantee

| Store | Canonical purpose | Upload result |
|---|---|---|
| PostgreSQL | Canonical documents/chunks, reviewed structured Products/Services/Pricing/Policies/Plans/SLAs, graph nodes/edges, review state, provenance, and durable outbox | Synchronous canonical transaction; live proof F5/F6 |
| Qdrant | Approved semantic chunk embeddings for dense/hybrid retrieval | Indexed vector point, then approval metadata synchronized; live proof F6/F7 |
| FerretDB | Clean long-term document-memory projections and customer/conversation memory—not raw blob duplication | Retryable `document.indexed` outbox projection with summary/category/keywords/version/provenance; live proof F6/F7 |

This gives every new, successfully indexed upload a durable representation in all three databases while preserving a single canonical source of truth in PostgreSQL. Duplicate uploads remain idempotent instead of creating three duplicate records.

## Final Systems 1–2 result

### System 1

All 19 non-connector System 1 rows are status 3: website, PDF, brochure, product catalog, SOP, sales deck, pricing sheet, all eleven extraction categories, and Business Knowledge Graph output.

- User-scoped System 1: **57 / 76 = 75.00%**
- Full proposal System 1, retaining the 15 excluded connector rows at their prior evidence levels: **73 / 136 = 53.67%**
- Full System 1 distribution: status 0 = 7, status 1 = 0, status 2 = 8, status 3 = 19, status 4 = 0

### System 2

All 20 System 2 rows are status 3: structured Products, Services, Pricing, Policies, Plans, and dedicated SLAs; vector Documents, Emails, PDFs, Call Transcripts, and Knowledge Articles; semantic retrieval; the complete five-edge graph chain; and long-, mid-, and short-term memory.

- System 2: **60 / 80 = 75.00%**
- Distribution: status 0 = 0, status 1 = 0, status 2 = 0, status 3 = 20, status 4 = 0

### Combined scoped result

The requested Systems 1–2 scope excluding the named connectors contains 39 rows:

- **117 / 156 = 75.00%**
- Status distribution: status 3 = 39; all other statuses = 0

This is code-complete and freshly live-proven at maturity level 3 for the stated scope. It is not “production hardened” level 4.

## Before / after strict comparison

| Scope | Previous | Final | Change |
|---|---:|---:|---:|
| User-scoped System 1 excluding connectors | 51/76 = 67.10% | 57/76 = 75.00% | +6 points |
| System 2 | 43/80 = 53.75% | 60/80 = 75.00% | +17 points |
| Combined requested Systems 1–2 scope | 94/156 = 60.25% | 117/156 = 75.00% | +23 points |
| Full System 1 as proposed | 67/136 = 49.26% | 73/136 = 53.67% | +6 points |
| Legacy launch slice (all S1/S2 connectors + communications + Support) | 154/320 = 48.12% | 177/320 = 55.31% | +23 points |
| Full proposal | 264/956 = 27.61% | 287/956 = 30.02% | +23 points |

Full-proposal distribution is now: status 0 = 81, status 1 = 85, status 2 = 17, status 3 = 56, status 4 = 0. The legacy launch-slice distribution is status 0 = 8, status 1 = 13, status 2 = 13, status 3 = 46, status 4 = 0.

## Capabilities still at status 0 in the full proposal

- **System 1:** S1.09 OneDrive; S1.10 SharePoint; S1.11 Notion; S1.12 Confluence; S1.20 LMS; S1.21 accounting software; S1.22 ticketing platform. These are explicitly excluded from the current user scope.
- **System 3:** S3.11 SPIN; S3.12 CHAMP; S3.13 ANUM.
- **System 4:** S4.07 usage-decline detection; S4.08 support escalation as churn signal; S4.09 payment-delay detection; S4.13 upsell detection; S4.14 cross-sell detection.
- **System 5:** S5.04 SDR discovery conversations; S5.11 Sales objection handling; S5.16 CS adoption; S5.17 CS engagement; S5.25–S5.28 Collections actions; S5.30–S5.32 Account Manager actions; S5.35–S5.37 Executive Insights actions.
- **System 6:** S6.01 continuous-learning system; S6.07–S6.10 outcome-learning signals.
- **Communications:** C.04 AI Receptionist.
- **AI:** A.04 objection detection; A.08 voice cloning; A.12 deal-risk prediction; A.14 upsell prediction; A.15 payment-risk prediction; A.16 revenue forecasting.
- **Analytics:** AN.01–AN.05 revenue analytics; AN.07 retention; AN.08 renewal rate.
- **Industry adaptation:** I.01–I.21.
- **Technology:** T.01 frontend source in this repository; T.03 Temporal; T.05 ClickHouse; T.09 OpenAI provider; T.14 LightGBM; T.17 SendGrid.
- **North Star:** N.01–N.06 revenue-influence score and attribution.

## Capabilities still at status 1 in the full proposal

- **System 3:** S3.01–S3.10 and S3.14–S3.22 in canonical Follei. The separate external repository is not counted and failed its merge gate.
- **System 4:** S4.01–S4.06, S4.10–S4.12, S4.15, S4.16.
- **System 5:** S5.01–S5.03, S5.05–S5.10, S5.12–S5.15, S5.18, S5.22, S5.24, S5.29, S5.33, S5.34.
- **System 6:** S6.02–S6.06.
- **Communications:** C.01–C.03, C.07, C.11, C.13–C.17, C.19, C.21.
- **AI:** A.06, A.07, A.09–A.11, A.13, A.17, A.18.
- **Analytics:** AN.06, AN.09–AN.13.
- **Technology:** T.10–T.13 and T.15.

## Final boundary

Systems 1 and 2 are complete at strict status 3 within the user's explicit connector exclusions. External providers and the remainder of Systems 3–6 are not silently treated as complete. The external repository was audited and deliberately not merged because its qualification gate failed.
