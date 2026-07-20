# Follei current-state handover

Prepared: 2026-07-20 (Asia/Kolkata)

This is a continuation handover, not a new completion audit. Continue the ordered work at the exact resume point below. Do not trust the older optimistic `94%/90%` claims; use the strict 0–4 audit baseline until Phase 8 recomputes it.

## Workspace and runtime

- Repository: `D:\pradeep-coirei\Follei-backend-Team`
- Canonical backend: `app\`
- Python: `follei_backend\indic_tts_venv\Scripts\python.exe`
- Current commit: `2df04419 new updates added`
- PostgreSQL, Redis, Kafka, Qdrant, FerretDB, MinIO/object storage, API, and indexing worker are local services.
- Use the current local `.env`; never print or paste its secret values.
- The local PostgreSQL/FerretDB/MinIO/JWT credentials were rotated. The rotation helper is `scripts\rotate_local_credentials.py`.
- Do not reset or discard the working tree. It contains the active stabilization work: 42 tracked modified files and 29 untracked entries.

Current literal health response:

```json
{"status":"healthy","services":{"api":"ok","postgres":"ok","redis":"ok","qdrant":"ok","kafka":"ok","ferretdb":"ok","object_storage":"ok"},"queues":{"indexing":{"queued":0,"processing":0,"retrying":0,"failed":0,"dead_lettered":1},"knowledge_sync":{"pending":0,"processing":0,"retrying":0}}}
```

The single dead-lettered indexing job is retained evidence from an intentional retry/DLQ failure test; it is not a currently queued failure.

## Strict completion baseline

The last row-by-row audit is `FOLLEI_FULL_PROPOSAL_AUDIT_2026-07-20.md`. Its scoring is evidence-weighted: 0 = absent, 1 = code only, 2 = tests only, 3 = live proof, 4 = production hardened.

| Scope | Strict baseline |
|---|---:|
| System 1 | 49.26% (67/136 points) |
| System 2 | 53.75% (43/80 points) |
| Selected launch slice: Systems 1–2, all communications, Support worker | 48.12% (154/320 points) |
| Full proposal | 27.61% (264/956 points) |

Do not increase these values in an interim report. Phase 8 is the one authorized final re-audit. The percentages are intentionally much lower than “feature count” percentages because unproved code is capped at status 1–2 and nothing has status 4 without production operations evidence.

## What is genuinely working now

### System 1

- Local infrastructure is healthy and Kafka indexing is operational.
- PDF, DOCX, TXT, CSV, XLSX, PPTX, EML/MSG body, image/scanned-PDF OCR, and layout-aware chunking have implementation and regression coverage. Several formats have retained live indexing evidence, but Phase 2 still requires fresh named evidence rows.
- Safe, tenant-scoped website ingestion exists with SSRF, public-address, same-domain, robots, page, and byte controls. It is a bounded knowledge crawler, not an unrestricted media-mirroring scraper.
- Persistent indexing jobs, retry/DLQ handling, object-storage source recovery, duplicate/new-version dispositions, and category-targeted extraction code exist.
- All onboarding knowledge categories have schemas/publishers/tests: products, services, pricing, plans, policies, FAQs, competitors, customer segments, sales processes, support processes, and payment processes.
- Human fact review can publish operational PostgreSQL records and enqueue Qdrant synchronization.

### System 2

- Chat combines hybrid document retrieval with orchestrator context rather than replacing document evidence.
- The orchestrator includes approved PostgreSQL facts, Qdrant evidence, PostgreSQL graph relations, FerretDB memory, provenance, and surfaced conflicts.
- PostgreSQL BM25, neighbour expansion, and Qdrant retrieval have approved-only filtering code and regression coverage.
- Chat citations can distinguish `qdrant_chunk`, `postgres_fact`, `graph_relation`, and `ferretdb_memory`.
- Conversation/onboarding memory, retrieval logging, conflict surfacing/resolution code, JWT tenant enforcement, and a shared worker-context contract exist and have varying levels of tests/live evidence.
- The Support worker’s local inbound email-shaped webhook was previously live-proven for grounded FAQ handling and escalation. That does not prove external email delivery.

### Not yet production-proven

- No status-4 capability exists. There is no completed backup/restore drill, production HA proof, long soak/load test, formal security review, or operational alerting proof.
- Real outbound campaigns/email/SMS/WhatsApp/voice delivery is not proven. Campaign routes were absent in the last OpenAPI evidence, and required provider settings are not fully declared in `Settings`.
- External connectors mostly have absent code or mocked tests, not live OAuth/provider reads.

## Exact current phase: Phase 1 is repaired but not gated

Required tenant: `87e38dbc-0218-4cd1-be7e-7d55721b2a07`

Affected draft: `f1d79e94-9e6b-4b23-aba9-90e69b60ec2e`

Source chunk: `7b60bb2d-4707-4b52-ab63-cc37a40567ed`

### Root cause

The inconsistency was produced by a legacy approval path, not a random current partial commit:

1. The old extractor stored this policy as `{"description":"The refund window is 45 days from the original purchase date."}`.
2. The old policy publisher read only `payload["body"]`, so it created a policy with `body = NULL`.
3. The old approval endpoint marked the draft approved but did not promote the PostgreSQL source chunk.
4. Its old Qdrant outbox payload omitted approval status/tags, leaving Qdrant at draft.

Historical code proving that old path is in commit `d0b46c5d`.

### Code added/fixed

- `app/services/knowledge/fact_publishing.py`
  - Canonicalizes legacy policy `description` into `body` at the publication boundary.
  - Validates the canonical payload before publishing.
  - Persists the canonical draft payload.
- `app/services/knowledge/approval_consistency.py`
  - Scans every approved draft for missing/null operational policy bodies or non-approved source chunks.
  - Repairs PostgreSQL atomically and resets/creates the retryable Qdrant outbox event.
- `scripts/backfill_approved_fact_consistency.py`
  - Runs the all-tenant repair, processes retryable events, and rescans.
- `tests/knowledge/test_fact_approval_store_consistency.py`
  - Uses real PostgreSQL and Qdrant.
  - Approves a legacy description-only policy.
  - Uses one combined assertion for non-null operational body, approved PostgreSQL chunk, and matching approved Qdrant payload.

### Literal regression result

```text
.......                                                                  [100%]
7 passed, 25 warnings in 7.64s
```

Command:

```powershell
$env:PYTHONPATH='.'
follei_backend\indic_tts_venv\Scripts\python.exe -m pytest tests\knowledge\test_fact_approval_store_consistency.py tests\knowledge\test_phase3_fact_review.py tests\knowledge\test_phase7_outbox.py -q
```

### Literal all-tenant backfill result

```json
{"approved_drafts_rescanned":5,"approved_drafts_scanned":5,"inconsistencies_found":1,"outbox_events_processed":1,"postgres_rows_repaired":1,"remaining":[],"remaining_inconsistencies":0,"repairs":[{"chunk_id":"7b60bb2d-4707-4b52-ab63-cc37a40567ed","draft_id":"f1d79e94-9e6b-4b23-aba9-90e69b60ec2e","fact_type":"policy","outbox_event_id":"fe3f2046-7e95-45fe-b566-edd91df5aaed","reasons":["operational_policy_body_null","source_chunk_not_approved"],"tenant_id":"87e38dbc-0218-4cd1-be7e-7d55721b2a07"}]}
```

### Fresh read after repair

```text
{'draft_status': 'approved', 'policy_id': 'a58020d2-701f-4be2-af1c-a9f075dbf5c1', 'policy_body': 'The refund window is 45 days from the original purchase date.', 'postgres_chunk_tags': ['category:policy', 'approval:approved'], 'outbox_id': 'fe3f2046-7e95-45fe-b566-edd91df5aaed', 'outbox_status': 'completed', 'outbox_deliveries': {'postgres': 'completed', 'qdrant': 'completed'}, 'qdrant_approval_status': 'approved', 'qdrant_tags': ['category:policy', 'approval:approved'], 'qdrant_approved_fact_id': 'f1d79e94-9e6b-4b23-aba9-90e69b60ec2e'}
```

### Exact resume action

Phase 1 is **not complete** because the user interrupted immediately before the required chat gate.

1. Restart the API and knowledge-sync/indexing workers so all current code is loaded.
2. Generate a short-lived tenant JWT without printing it.
3. Send a fresh authenticated `POST http://127.0.0.1:8000/chat/` with:

```json
{"tenant_id":"87e38dbc-0218-4cd1-be7e-7d55721b2a07","question":"What is the refund window?"}
```

4. Paste the complete literal HTTP response.
5. Gate passes only if the answer contains `45 days`, `supported` is `true`, and citations are non-empty.
6. If it fails, diagnose and fix it before Phase 2. Do not claim Phase 1 complete from the database/Qdrant proof alone.

## Remaining ordered work

### Phase 2 — twelve fresh Category A live rows

Produce and prove, through live ingestion/approval as applicable:

- Brochure, Product Catalog, and SOP through Kafka.
- Competitor, Customer Segment, and Payment Process approved facts.
- Approved structured Product and Service records.
- One dedicated SLA record.
- One Call Transcript and one Knowledge Article vector document.
- One live Product → Feature graph edge.

Gate: 12 rows, each with real draft/document/operational IDs and literal PostgreSQL/Qdrant query output.

### Phase 3 — missing graph relationships

Implement/test/live-prove:

- Feature → Benefit.
- Benefit → Customer Segment.
- Customer Segment → Objection.
- Objection → Response, including the missing Response node/model.

Gate: one literal live graph row and one chat `graph_relation` citation for each of the four edges.

### Phase 4 — unified test suite

- Declare `Settings.AI_MODELS` and fix all nine AI-suite failures without skipping/deleting tests.
- Fold the main tests, MCP tests, and AI tests into one pytest command/collection.
- Prior retained baselines: main `192 passed`; MCP `48 passed`; AI `19 passed, 9 failed`.

Gate: one command, all three original directories collected, zero failures, literal total.

### Phase 5 — live connectors

In order: Notion, Confluence, Slack, owned LMS, Microsoft Graph (Outlook/OneDrive/SharePoint/Teams), Google OAuth (Drive/Gmail), HubSpot sandbox, Odoo Community ERP.

Code/mocked tests are status 1–2. Status 3 requires real OAuth/provider credentials, a real read, and ingestion evidence. Provider/account setup is an external dependency and must not be faked.

### Phase 6 — external repository audit

Clone and audit:

`https://github.com/vijayalakshmi270605/enterprise-ai-agent-new-changes-`

Score S3.01–S3.22 plus real STT, TTS, translation artifacts, callable-service status, and secret scan. This has not started in the current ordered pass.

### Phase 7 — conditional System 3 merge

Merge only if the Phase 6 qualification gate passes. Do not merge wholesale; isolate heavy STT/TTS/ML runtimes as microservices and reuse Follei’s tenant-scoped PostgreSQL/Qdrant/FerretDB model. Otherwise stop with literal reasons.

### Phase 8 — single final audit

Only here recompute the strict scores, evidence catalog, status-0/status-1 lists, and before/after comparison against System 1 `49.26%`, System 2 `53.75%`, launch slice `48.12%`, and full proposal `27.61%`.

## Important repository cautions

- Preserve all current changes; do not run `git reset --hard`, checkout modified files, or clean untracked files.
- No Phase 1 commit has been created.
- Do not print `.env`, tokens, passwords, API keys, connection strings, or Authorization headers.
- The credentials shown in earlier chat messages must be treated as exposed even though local values were rotated. Provider-side rotation still requires the corresponding provider dashboards where applicable.
- The prior handover’s `94%/90%` statements are feature/demo-slice estimates and conflict with the required strict 0–4 rubric. Use the strict audit numbers.
- Do not skip phases or run another completion audit before Phase 8.

## Copy/paste continuation prompt

```text
Continue the ordered Follei work from FOLLEI_CURRENT_HANDOVER_2026-07-20.md. Work only from the exact resume point. Preserve the dirty working tree and never print secrets. Phase 1 code, combined live-store regression, all-tenant backfill, and PostgreSQL/Qdrant verification are complete, but Phase 1 is NOT gated yet. Restart the current services, issue a fresh authenticated POST /chat/ for tenant 87e38dbc-0218-4cd1-be7e-7d55721b2a07 asking “What is the refund window?”, and paste the complete literal response. Do not begin Phase 2 unless it contains “45 days”, supported:true, and non-empty citations. Then continue Phases 2–8 in the written order with every literal gate; do not give interim completion percentages or run the final audit early.
```
