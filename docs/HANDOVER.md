# Follei backend handover

For the current 2026-08-31 project and Voice AI verification handover, including
training, accent/prosody adaptation, consented voice cloning, latency, and
concurrency, see `docs/FOLLEI_PROJECT_AND_VOICE_HANDOVER_2026-08-31.md`.

Status date: 2026-08-10

## Working baseline

- Canonical branch: `main`
- Historical recovery branch: `old-follei`
- Pre-light-runtime recovery branch: `backup/pre-light-runtime-20260810`
- API contract: `/openapi.json`; interactive reference: `/docs`
- Current full application schema: 177 API paths and 241 operations

The recovery branches retain every file removed by the runtime cleanup,
including the nested CRM prototype and generated audio samples.

## Default runtime

`./start.sh` and `start.bat` now start only these application processes:

1. API: authentication, OAuth, onboarding/readiness, ingestion, verification,
   and retrieval/generation.
2. Indexing worker: parse, classify, structure-aware chunk, batch-embed.
3. Knowledge-sync worker: PostgreSQL outbox projection to FerretDB/Qdrant.
4. Google Workspace worker: independent Gmail, Drive, Contacts, and Calendar
   synchronization.
5. Website ingestion worker: consent-aware, SSRF/robots/domain-safe crawling.

Required infrastructure remains PostgreSQL, Redis, Kafka/Zookeeper, MinIO,
FerretDB/DocumentDB, and Qdrant. These are storage/queue dependencies, not
additional business workers.

The optional `--full` profile adds analysis, lead scoring, mail automation,
flow execution, and HubSpot sync. Local Torch/Transformers and voice packages
are isolated in `requirements-optional-ai.txt`; they are not installed or
loaded by the default profile.

## Primary frontend APIs

### Authentication

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET|PATCH /api/v1/auth/me`
- `POST /api/v1/auth/password/change`
- `POST /api/v1/auth/password/reset-request`
- `POST /api/v1/auth/password/reset`

### Onboarding and readiness

- `POST|PATCH /api/v1/onboarding/profile`
- `PATCH /api/v1/onboarding/user-profile`
- `GET /api/v1/onboarding/status`
- `GET /api/v1/onboarding/taxonomy`
- `GET /api/v1/onboarding/state`
- `POST /api/v1/onboarding/confirmations`
- `GET /api/v1/onboarding/extractions`
- `PATCH /api/v1/onboarding/extractions/{draft_id}`
- `POST /api/v1/onboarding/complete`

### File and knowledge ingestion

- `POST /upload/`
- `GET /upload/jobs/{job_id}`
- `POST /upload/jobs/{job_id}/retry`
- `GET /upload/documents/{document_id}/status`
- `GET /upload/documents/{document_id}/extraction`
- `GET /upload/documents/{document_id}/storage-verification`
- `GET /api/v1/knowledge/websites/engines`
- `POST /api/v1/knowledge/websites/ingest`

### Google Workspace

- `POST /api/v1/integrations/google-workspace/oauth/start`
- `GET /api/v1/integrations/google-workspace/oauth/callback`
- `GET /api/v1/integrations/google-workspace/connections`
- `POST /api/v1/integrations/google-workspace/connections/{connection_id}/sync`

Google currently syncs Gmail message bodies and attachments, Drive file
content (including supported Google-native exports), Contacts, and Calendar.
Each resource has an independent job, cursor, failure, and retry path.

### Retrieval and review

- `POST /api/v1/knowledge/query` — tenant-filtered Qdrant retrieval plus
  Mistral generation, streamed as SSE.
- `GET /knowledge/review/facts/drafts`
- `GET|PATCH /knowledge/review/facts/{draft_id}`
- `POST /knowledge/review/facts/{draft_id}/approve`
- `POST /knowledge/review/facts/{draft_id}/reject`
- `POST /knowledge/review/conflicts/resolve`

### Lead import

- `POST /api/leads/import/preview`
- `POST /api/leads/import/async`
- `POST /api/leads/import/upload`
- `GET /api/leads/import/{job_id}`
- `GET /api/leads/import/{job_id}/preview`
- `POST /api/leads/import/{job_id}/commit`
- `PUT /api/leads/import/{job_id}/rows/{row_id}`
- `POST /api/leads/import/{job_id}/rows/{row_id}/ignore`
- `POST /api/leads/import/{job_id}/bulk`
- `POST /api/leads/import/{job_id}/crawl-links`
- `GET /api/leads/import/{job_id}/storage-verification`

Contactability is resolved per tenant: default one valid contact method,
matched against active channel connections; the tenant can raise the required
count. The import response reports the resolved policy.

### HubSpot (optional profile)

- `POST /api/v1/crm/hubspot/oauth/start`
- `GET /api/v1/crm/hubspot/oauth/callback`
- `GET /api/v1/crm/connections`
- `DELETE /api/v1/crm/hubspot/connections`
- `POST /api/v1/crm/hubspot/sync`
- `GET /api/v1/crm/records`
- `GET /api/v1/crm/sync-runs`

Implemented resources: contacts, companies, deals. Deferred resources:
owners, pipelines, associations, property schemas, and engagements.

## Retrieval/generation status

- Mistral embedding and chat adapters: complete.
- Shared ingestion/query embedding model config: complete.
- Batch ingestion embeddings: complete.
- Mandatory tenant and optional category Qdrant filters: complete.
- Context includes `heading_path`, `chunk_type`, and `source_id`: complete.
- SSE token streaming and clean provider timeout/rate-limit errors: complete.
- Live Mistral calls require a valid `MISTRAL_API_KEY`; automated tests use a
  mocked provider and do not spend provider quota.

## Removed from the canonical branch

- Duplicate nested `Server_crm-main` prototype.
- Five empty TODO-only worker modules.
- Obsolete Windows Terminal launcher helper.
- Tracked debug WAV and generated TTS MP3 runtime output.

These remain recoverable from `backup/pre-light-runtime-20260810` and
`old-follei`; runtime output directories are now ignored.

## Verification record

- Full suite: 378 passed, 0 failed, 0 skipped against live services.
- Clean PostgreSQL: empty database upgraded to head, `alembic check` clean,
  downgraded to base, and cleaned up.
- Current database head: `20260810_tenant_defaults`.
- Live Qdrant and FerretDB tenant-scoped round trips: passed.
- Default five-service startup and healthy aggregate health check: passed.
- Linux shell syntax/compile checks: passed.
- Windows launcher was structurally reviewed and shares the tested service
  profile, but cannot be executed on this Linux host.

## Remaining work

- Implement the five deferred HubSpot resources if/when they enter scope.
- Run a provider-quota Mistral smoke query in the deployment environment.
- Install Playwright Chromium with `--install-browser` where JavaScript-only
  sites must be crawled.
- Address non-blocking deprecation warnings (`datetime.utcnow`, FastAPI
  `on_event`, Pydantic class `Config`, and Qdrant `recreate_collection`).
