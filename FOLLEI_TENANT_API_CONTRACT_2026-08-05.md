# Follei Tenant Setup API Contract

**Status date:** 2026-08-05  
**Scope:** Tenant registration, onboarding, company knowledge ingestion, extraction review, email, HubSpot CRM sync, lead import, and the Insurance workflow runtime.  
**Source of truth:** The routes and schemas currently implemented in this repository.

## 1. What is runnable now

The current backend supports this setup sequence:

1. Register one user and one tenant.
2. Save the tenant's company profile and the registering user's profile.
3. Select `Financial Services` to instantiate the current Insurance workflow pack.
4. Upload company documents and/or ingest an authorized company website.
5. Poll asynchronous ingestion jobs and review extracted company facts.
6. Connect Gmail or Brevo.
7. Connect one HubSpot account and synchronize contacts, companies, and deals.
8. Import leads, review the parsed rows, and commit selected leads.
9. Activate the Insurance workflow, submit structured conversation outcomes, upload structured application fields, make human approval decisions, and retrieve the case audit.

The frontend must never write directly to PostgreSQL, FerretDB, or Qdrant. It calls these APIs only. The backend controls all three stores:

| Store | Current responsibility |
|---|---|
| PostgreSQL | Canonical tenants, users, onboarding profile, approved knowledge, leads/customers, CRM records, workflow state, approvals, and audit |
| FerretDB | Flexible/raw source payloads and projections such as raw CRM objects and conversation context |
| Qdrant | Rebuildable semantic-search vectors for company knowledge and CRM summaries |

## 2. Known contract gaps that must not be hidden from the frontend team

These are planned behaviors, not completed API guarantees:

- Industry is currently optional in the backend. The frontend should require it, but the backend must still be changed to enforce it.
- The onboarding enum does not contain `Insurance`. For the current build, send `Financial Services`; it activates the Insurance pack. This naming mismatch should be corrected before freezing a public v1 contract.
- Registration creates the generic tenant flow, but industry-pack selection happens later through onboarding.
- HubSpot currently uses an access token/private-app token. HubSpot OAuth, refresh-token lifecycle, and webhook-driven delta sync are not implemented.
- CRM synchronization stores normalized data in PostgreSQL and creates projection events for FerretDB/Qdrant. It does not automatically declare a lead to be a customer.
- Manual lead-to-customer conversion and optional invoice entry do not yet have the dedicated APIs required by the agreed product plan.
- Gmail OAuth is implemented, but provider delivery receipts, bounce behavior, retries, and outage handling are not yet fully production-proven.
- Password reset endpoints exist as placeholders and are not part of this recommended runnable contract.
- Claims, renewals, final underwriting, policy binding, premium exceptions, and policy issuance are outside this slice.

## 3. Common HTTP contract

Local base URL:

```text
http://127.0.0.1:8000
```

Interactive OpenAPI documentation:

```text
http://127.0.0.1:8000/docs
```

All protected endpoints use:

```http
Authorization: Bearer <ACCESS_TOKEN>
```

JSON requests also use:

```http
Content-Type: application/json
```

Representative error format:

```json
{
  "detail": "Human-readable error"
}
```

Validation errors use HTTP `422`. Common status codes are `400` invalid operation, `401` invalid/missing credentials, `404` tenant-owned record not found, `409` state conflict or duplicate, `422` schema/policy validation failure, `502` upstream provider failure, and `503` required infrastructure unavailable.

The examples below use these shell placeholders:

```bash
FOLLEI_URL="http://127.0.0.1:8000"
ACCESS_TOKEN="replace-after-register-or-login"
TENANT_ID="replace-after-register-or-login"
```

## 4. Recommended tenant-registration sequence

### 4.1 Register account and tenant

`POST /api/v1/auth/register` — public

Request:

```json
{
  "email": "owner@acmeinsurance.example",
  "password": "StrongPass123",
  "full_name": "Asha Menon",
  "tenant_name": "Acme Insurance Services",
  "business_email": "sales@acmeinsurance.example",
  "connect_gmail": false,
  "gmail_auto_reply_enabled": true,
  "gmail_campaign_enabled": true,
  "email_connections": []
}
```

Rules:

- Password: 8–128 characters with at least one letter and one number.
- `email_connections` is optional and accepts at most two connections.
- Prefer connecting Gmail through OAuth after registration instead of putting an app password in registration.
- Registration creates an admin user, tenant, default inactive flow, and universal tenant workflow runtime.

Example:

```bash
curl -sS -X POST "$FOLLEI_URL/api/v1/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{
    "email":"owner@acmeinsurance.example",
    "password":"StrongPass123",
    "full_name":"Asha Menon",
    "tenant_name":"Acme Insurance Services",
    "business_email":"sales@acmeinsurance.example",
    "connect_gmail":false,
    "email_connections":[]
  }'
```

Response `201`:

```json
{
  "user_id": "d68fc30e-...",
  "tenant_id": "a47ca94b-...",
  "access_token": "<JWT>",
  "token_type": "bearer",
  "refresh_token": "<JWT>",
  "expires_in": 3600
}
```

The client must securely retain `access_token`, `refresh_token`, and `tenant_id`. Tenant identity on normal protected APIs comes from the access token, not an editable UI field.

### 4.2 Login

`POST /api/v1/auth/login` — public

Request:

```json
{
  "email": "owner@acmeinsurance.example",
  "password": "StrongPass123"
}
```

Response `200`:

```json
{
  "access_token": "<JWT>",
  "token_type": "bearer",
  "refresh_token": "<JWT>",
  "expires_in": 3600,
  "user": {
    "id": "d68fc30e-...",
    "email": "owner@acmeinsurance.example",
    "full_name": "Asha Menon",
    "tenant_id": "a47ca94b-...",
    "roles": ["admin"]
  }
}
```

### 4.3 Refresh access token

`POST /api/v1/auth/refresh` — public with refresh token in body

Request:

```json
{"refresh_token":"<REFRESH_TOKEN>"}
```

Response:

```json
{"access_token":"<NEW_JWT>","expires_in":3600}
```

### 4.4 Read current identity

`GET /api/v1/auth/me` — protected

Response:

```json
{
  "id": "d68fc30e-...",
  "email": "owner@acmeinsurance.example",
  "full_name": "Asha Menon",
  "tenant_id": "a47ca94b-...",
  "tenant_name": "Acme Insurance Services",
  "roles": ["admin"],
  "permissions": [],
  "created_at": "2026-08-05T10:00:00Z",
  "last_login": "2026-08-05T10:00:00Z"
}
```

## 5. Company and user onboarding

### 5.1 Create company profile and select industry

`POST /api/v1/onboarding/profile` — protected

For the current Insurance build, use this request:

```json
{
  "company_name": "Acme Insurance Services",
  "website": "https://acmeinsurance.example",
  "timezone": "Asia/Kolkata",
  "country_region": "India",
  "industry": "Financial Services",
  "company_size": "11-50",
  "contact_channels": ["Email", "Phone"],
  "goals": ["Increase Revenue", "Improve Conversion Rate"]
}
```

Allowed `industry` values today:

```text
SaaS
E-commerce
Financial Services
Healthcare
Education
Logistics & Transportation
Manufacturing
IT Services & Consulting
Telecommunications
Real Estate
Media & Entertainment
Other
```

When industry is `Other`, `industry_other` may contain the custom value. Allowed `company_size`: `1-10`, `11-50`, `51-200`, `201-1000`, `1000+`. Allowed channels: `Email`, `Phone`, `SMS`, `WhatsApp`. At most three goals are allowed.

Response:

```json
{
  "id": "<PROFILE_ID>",
  "tenant_id": "a47ca94b-...",
  "company_name": "Acme Insurance Services",
  "website": "https://acmeinsurance.example",
  "timezone": "Asia/Kolkata",
  "country_region": "India",
  "industry": "Financial Services",
  "industry_other": null,
  "company_size": "11-50",
  "contact_channels": ["Email", "Phone"],
  "goals": ["Increase Revenue", "Improve Conversion Rate"]
}
```

`PATCH /api/v1/onboarding/profile` accepts the same fields optionally and returns the complete updated profile.

### 5.2 Update registering user's onboarding details

`PATCH /api/v1/onboarding/user-profile` — protected

Request:

```json
{
  "full_name": "Asha Menon",
  "mobile_number": "+919876543210",
  "job_title": "Sales Director",
  "terms_accepted": true
}
```

Response:

```json
{
  "id": "d68fc30e-...",
  "tenant_id": "a47ca94b-...",
  "email": "owner@acmeinsurance.example",
  "full_name": "Asha Menon",
  "mobile_number": "+919876543210",
  "job_title": "Sales Director",
  "terms_accepted": true
}
```

### 5.3 Check onboarding status

`GET /api/v1/onboarding/status` — protected

Response:

```json
{
  "tenant_id": "a47ca94b-...",
  "profile_exists": true,
  "complete": true,
  "missing_fields": [],
  "documents": []
}
```

Today `complete` checks only `company_name` and `timezone`. The product UI should additionally require industry selection.

### 5.4 Complete onboarding

`POST /api/v1/onboarding/complete` — protected; no request body

Response:

```json
{
  "tenant_id": "a47ca94b-...",
  "completed_at": "2026-08-05T10:15:00Z",
  "already_completed": false,
  "pending_review_count": 4
}
```

Completion does not wait for all extracted facts to be reviewed. Pending facts remain available later.

## 6. Upload tenant company knowledge

These endpoints ingest the tenant's own products, services, pricing, policy documents, scripts, and processes. They do not expect the tenant to upload general industry knowledge.

Allowed categories:

```text
products, services, pricing, plans, policies, faqs, competitors,
customer_segments, sales_processes, support_processes, payment_processes, general
```

### 6.1 Upload a company document

`POST /upload/` — protected multipart form

Fields:

| Field | Required | Meaning |
|---|---:|---|
| `file` | Yes | PDF, DOCX, TXT, CSV, XLSX, PPT/PPTX, EML/MSG, PNG/JPG/TIFF |
| `tenant_id` | Yes | Must equal the tenant in the JWT |
| `source_uri` | No | Stable original source URI |
| `uploaded_by` | No | User/system label |
| `primary_category` | No | One category above |
| `workspace_id` | No | UUID for an optional workspace |
| `processing_instructions` | No | Up to 4,000 characters |

Example:

```bash
curl -sS -X POST "$FOLLEI_URL/upload/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -F "tenant_id=$TENANT_ID" \
  -F "file=@/absolute/path/company-products.pdf" \
  -F "primary_category=products" \
  -F "uploaded_by=tenant_admin"
```

Response:

```json
{
  "job_id": "<JOB_UUID>",
  "document_id": null,
  "tenant_id": "a47ca94b-...",
  "filename": "company-products.pdf",
  "source_uri": "upload://...",
  "primary_category": "products",
  "target_category": "products",
  "workspace_id": null,
  "status": "queued",
  "disposition": "pending",
  "message": "File uploaded and queued for idempotent indexing"
}
```

### 6.2 Poll upload job

`GET /upload/jobs/{job_id}` — protected

Response:

```json
{
  "job_id": "<JOB_UUID>",
  "tenant_id": "a47ca94b-...",
  "document_id": "<DOCUMENT_UUID>",
  "status": "completed",
  "disposition": "indexed",
  "attempt_count": 1,
  "last_error": null,
  "created_at": "...",
  "started_at": "...",
  "completed_at": "...",
  "payload": {}
}
```

Use `document_id` from the completed job for subsequent document endpoints.

`POST /upload/jobs/{job_id}/retry` retries only a failed/retrying/dead-lettered job and returns the same job shape.

### 6.3 Read processed document state

- `GET /upload/documents/{document_id}/status`
- `GET /upload/documents/{document_id}/extraction`
- `GET /upload/documents/{document_id}/storage-verification`

Storage-verification response shape:

```json
{
  "postgres": {
    "document_exists": true,
    "section_count": 8,
    "chunk_count": 24,
    "entity_count": 6,
    "fact_count": 12
  },
  "qdrant": {"indexed": true, "point_count": 24},
  "ferretdb": {
    "projected": true,
    "document_view_exists": true,
    "entity_projection_count": 6
  },
  "minio": {"original_exists": true},
  "consistent": true,
  "warnings": []
}
```

### 6.4 Ingest an authorized company website

`POST /knowledge/websites/ingest` — protected

Request:

```json
{
  "url": "https://acmeinsurance.example",
  "max_pages": 10,
  "category": "general",
  "confirm_authorized": true
}
```

Response:

```json
{
  "job_id": "<PRIMARY_JOB_UUID>",
  "asset_job_ids": ["<ASSET_JOB_UUID>"],
  "status": "queued",
  "source_uri": "https://acmeinsurance.example/",
  "pages_crawled": 10,
  "assets_discovered": 1,
  "disposition": "pending"
}
```

Poll each returned job with `GET /upload/jobs/{job_id}`.

## 7. Review AI-extracted company facts

AI extraction produces drafts. It does not approve its own facts.

### 7.1 List drafts

`GET /knowledge/review/facts/drafts?tenant_id={tenant_id}&status=draft&limit=50`

Response is an array:

```json
[
  {
    "id": "<DRAFT_UUID>",
    "tenant_id": "a47ca94b-...",
    "document_id": "<DOCUMENT_UUID>",
    "chunk_id": "<CHUNK_UUID>",
    "fact_type": "product",
    "payload": {"name": "Family Health Plan"},
    "citation": {"page": 3},
    "extraction_confidence": 0.91,
    "approval_status": "draft",
    "reviewer": null,
    "review_reason": null,
    "published_record_type": null,
    "published_record_id": null,
    "created_at": "...",
    "reviewed_at": null
  }
]
```

### 7.2 Edit a draft

`PATCH /knowledge/review/facts/{draft_id}`

```json
{
  "tenant_id": "a47ca94b-...",
  "payload": {"name": "Family Health Plan", "coverage_limit": 1000000},
  "reviewer": "Asha Menon",
  "reason": "Corrected coverage limit from the approved brochure"
}
```

### 7.3 Approve or reject a draft

- `POST /knowledge/review/facts/{draft_id}/approve`
- `POST /knowledge/review/facts/{draft_id}/reject`

Request:

```json
{
  "tenant_id": "a47ca94b-...",
  "reviewer": "Asha Menon",
  "reason": "Verified against current company policy document"
}
```

Both return the full draft shape with `approval_status` changed. Approval publishes the canonical fact to PostgreSQL and queues its derived projections.

## 8. Connect communication channels

### 8.1 Recommended Gmail OAuth flow

`POST /api/email-connections/gmail/oauth/start` — protected

Request:

```json
{
  "email_address": "sales@acmeinsurance.example",
  "sender_name": "Acme Insurance",
  "auto_reply_enabled": true,
  "allow_inbound_lead_creation": true,
  "campaign_enabled": true
}
```

Response:

```json
{
  "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "expires_in": 600
}
```

The frontend opens `authorization_url`. Google returns to:

`GET /api/email-connections/gmail/oauth/callback?state={state}&code={code}`

The backend then redirects to the configured frontend success URL with either `gmail_oauth=connected` or `gmail_oauth=error`.

### 8.2 Direct Gmail app-password or Brevo connection

`POST /api/email-connections` — protected

Gmail request:

```json
{
  "provider": "gmail",
  "email_address": "sales@acmeinsurance.example",
  "sender_name": "Acme Insurance",
  "app_password": "<GMAIL_APP_PASSWORD>",
  "auto_reply_enabled": true,
  "allow_inbound_lead_creation": true,
  "campaign_enabled": true
}
```

Brevo request:

```json
{
  "provider": "brevo",
  "email_address": "campaigns@acmeinsurance.example",
  "sender_name": "Acme Insurance",
  "api_key": "<BREVO_API_KEY>",
  "campaign_enabled": true
}
```

Response `201`:

```json
{
  "id": "<CONNECTION_UUID>",
  "provider": "gmail",
  "email_address": "sales@acmeinsurance.example",
  "sender_name": "Acme Insurance",
  "enabled": true,
  "verified": false,
  "auto_reply_enabled": true,
  "allow_inbound_lead_creation": true,
  "campaign_enabled": true,
  "status": "configured",
  "has_api_key": false,
  "has_app_password": true,
  "auth_type": "app_password",
  "oauth_connected": false,
  "inbound_ready": false,
  "last_polled_at": null,
  "last_error": null,
  "created_at": "...",
  "updated_at": "..."
}
```

Management endpoints:

- `GET /api/email-connections` — list tenant connections.
- `PATCH /api/email-connections/{connection_id}` — update address, sender name, credentials, enabled state, and feature flags.
- `DELETE /api/email-connections/{connection_id}` — disconnect/revoke; returns `204`.

Secrets are accepted only in requests. Responses expose boolean `has_*` values, never the secret itself.

## 9. HubSpot CRM synchronization

Only HubSpot is supported in the completed three-store CRM path. Apply the current Alembic migration before calling these endpoints.

### 9.1 Connect HubSpot

`POST /api/v1/crm/hubspot/connections` — protected

Request:

```json
{
  "access_token": "<HUBSPOT_PRIVATE_APP_ACCESS_TOKEN>",
  "validate_connection": true
}
```

Response `201`:

```json
{
  "id": "<CRM_CONNECTION_UUID>",
  "provider": "hubspot",
  "status": "active",
  "external_account_id": null,
  "scopes": [],
  "last_synced_at": null,
  "last_error": null
}
```

The access token is encrypted before storage and is never returned.

### 9.2 Run CRM sync

`POST /api/v1/crm/hubspot/sync` — protected

Request:

```json
{
  "resources": ["contact", "company", "deal"],
  "page_size": 100,
  "max_pages_per_resource": 10,
  "project_now": false
}
```

Response `202`:

```json
{
  "id": "<SYNC_RUN_UUID>",
  "provider": "hubspot",
  "status": "completed",
  "object_counts": {"contact": 250, "company": 20, "deal": 45},
  "projection_event_count": 315,
  "error": null
}
```

Keep `project_now=false` in normal operation. It records PostgreSQL state plus outbox events, and the knowledge-sync worker builds FerretDB/Qdrant projections. `project_now=true` is primarily useful for controlled development runs.

### 9.3 Inspect synchronized records

`GET /api/v1/crm/records?object_type=contact&limit=100`

Response:

```json
[
  {
    "id": "<CRM_RECORD_UUID>",
    "provider": "hubspot",
    "object_type": "contact",
    "external_id": "12345",
    "lead_id": "<MATCHED_LEAD_UUID>",
    "customer_id": null,
    "canonical_data": {
      "email": "lead@example.com",
      "first_name": "Ravi",
      "last_name": "Kumar"
    },
    "source_revision": 1,
    "synced_at": "2026-08-05T11:00:00Z"
  }
]
```

`object_type` may be `contact`, `company`, or `deal`.

Additional CRM endpoints:

- `GET /api/v1/crm/connections`
- `GET /api/v1/crm/sync-runs?limit=50`
- `DELETE /api/v1/crm/hubspot/connections` — disconnects and deletes the stored token; returns `204`.

## 10. Lead upload, review, and commit

The recommended path is the reviewable import-job API. Although the route and response text still describe background processing, the current `/upload` implementation awaits the parsing/extraction pipeline before returning. A normal successful upload therefore returns `preview_ready`; treat it as a potentially long HTTP request until the processing worker/API boundary is separated.

### 10.1 Upload leads

`POST /api/leads/import/upload` — protected multipart form

```bash
curl -sS -X POST "$FOLLEI_URL/api/leads/import/upload" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -F "tenant_id=$TENANT_ID" \
  -F "file=@/absolute/path/leads.xlsx"
```

Response `201`:

```json
{
  "job_id": "<IMPORT_JOB_UUID>",
  "public_id": "LIMP-...",
  "filename": "leads.xlsx",
  "file_type": "xlsx",
  "status": "preview_ready",
  "message": "File uploaded successfully. Processing in background."
}
```

### 10.2 Poll import status

`GET /api/leads/import/{job_id}` — protected

```json
{
  "id": "<IMPORT_JOB_UUID>",
  "public_id": "LIMP-...",
  "tenant_id": "a47ca94b-...",
  "filename": "leads.xlsx",
  "file_type": "xlsx",
  "status": "preview_ready",
  "uploaded_by": "d68fc30e-...",
  "total_rows": 100,
  "valid_rows": 88,
  "duplicate_rows": 7,
  "invalid_rows": 5,
  "statistics": {},
  "error_message": null,
  "created_at": "...",
  "completed_at": "..."
}
```

### 10.3 Preview and classify rows

`GET /api/leads/import/{job_id}/preview`

The response contains `new_rows`, `update_rows`, `duplicate_rows`, `conflict_rows`, `invalid_rows`, `spam_rows`, `needs_review_rows`, and `ignored_rows`. Each row includes:

```json
{
  "id": "<ROW_UUID>",
  "row_index": 2,
  "raw_data": {},
  "normalized_data": {"email": "lead@example.com"},
  "extracted_data": {},
  "confidence": 0.96,
  "confidence_reason": "Email and phone parsed",
  "duplicate_probability": 0,
  "source_page": null,
  "source_row": 2,
  "quality_score": 92,
  "quality_grade": "A",
  "quality_reasons": [],
  "quality_flags": [],
  "intelligence": {},
  "duplicate": false,
  "duplicate_of": null,
  "match_reason": null,
  "status": "valid",
  "selected": true,
  "error": null
}
```

Review operations:

- `PUT /api/leads/import/{job_id}/rows/{row_id}` with `{"updates":{"email":"corrected@example.com"}}`.
- `POST /api/leads/import/{job_id}/rows/{row_id}/ignore` with no body.
- `POST /api/leads/import/{job_id}/bulk` with `{"action":"select","row_ids":["<UUID>"]}`. Actions: `ignore`, `reset`, `spam`, `select`, `deselect`.

### 10.4 Commit selected leads

`POST /api/leads/import/{job_id}/commit` — no request body

Response:

```json
{
  "job_id": "<IMPORT_JOB_UUID>",
  "public_id": "LIMP-...",
  "status": "committed",
  "total_imported": 88,
  "total_new": 80,
  "total_updated": 8,
  "total_duplicates": 7,
  "total_conflicts": 0,
  "total_invalid": 5,
  "message": "Import committed successfully",
  "flow_enrollment": {}
}
```

Optional post-commit endpoints:

- `POST /api/leads/import/{job_id}/crawl-links?confirm_authorized=true` — ingest websites found in committed lead data only when authorized.
- `GET /api/leads/import/{job_id}/storage-verification` — verify the import's persistence/projection state.

There is also a small synchronous CSV endpoint at `POST /api/leads/import`, but the job-based flow above is the supported UI contract because it provides preview, correction, dedupe decisions, and explicit commit.

## 11. Insurance workflow runtime

### 11.1 Instantiate/activate the tenant's Insurance workflow pack

`POST /api/v1/flows/instances/insurance` — protected; no body

Response `201` is an object containing the root and child instances. Each value has:

```json
{
  "id": "<INSTANCE_UUID>",
  "public_id": "...",
  "template_id": "<TEMPLATE_UUID>",
  "flow_id": "<FLOW_UUID>",
  "parent_instance_id": null,
  "parent_node_key": null,
  "name": "Insurance / Lead-to-Application",
  "status": "active",
  "overrides": {},
  "created_at": "..."
}
```

Supporting setup endpoints:

- `GET /api/v1/flows/templates` — published industry templates and node contracts.
- `GET /api/v1/flows/instances` — this tenant's root and nested workflow instances.
- `PATCH /api/v1/flows/instances/{instance_id}/overrides` with `{"overrides":{...}}` — creates a draft override version.
- `POST /api/v1/flows/instances/{instance_id}/activate` — validates and activates that draft.
- `GET /api/v1/flows/readiness` — checks graph and email readiness.

The operational flow endpoints used to find and start enrollments are:

- `GET /api/v1/flows` — list tenant flows and obtain `flow_id`.
- `GET /api/v1/flows/{flow_id}` — read one graph/version.
- `PATCH /api/v1/flows/{flow_id}/draft` — save a graph draft with `{"graph":{...},"settings":{...},"name":"..."}`.
- `POST /api/v1/flows/{flow_id}/validate` — return graph errors and email readiness.
- `POST /api/v1/flows/{flow_id}/activate` — publish the current version; email flows require enabled Gmail OAuth.
- `POST /api/v1/flows/{flow_id}/pause` — pause new execution.
- `POST /api/v1/flows/{flow_id}/enroll-existing` — body `{"mode":"all_eligible","lead_ids":[]}` or `{"mode":"selected","lead_ids":["<LEAD_UUID>"]}`.
- `GET /api/v1/flows/{flow_id}/enrollments` — obtain the `enrollment_id`, status, and current node required by the event/document APIs below.

### 11.2 Submit first-contact outcome

`POST /api/v1/flows/enrollments/{enrollment_id}/event`

Allowed outcomes:

```text
connected_interested, connected_busy, no_answer, not_interested, requests_human
```

Every first-contact event requires `channel`.

Connected and interested:

```json
{
  "event": "connected_interested",
  "payload": {
    "channel": "phone",
    "contact_receipt_id": "provider-call-123",
    "consent_to_continue": true,
    "product_interest": "family_health",
    "urgency": "within_30_days",
    "objections": ["price"],
    "qualification_evidence": {
      "need": "family coverage",
      "timeline": "30 days"
    }
  }
}
```

Connected but busy additionally requires `preferred_callback_at`:

```json
{
  "event": "connected_busy",
  "payload": {
    "channel": "phone",
    "preferred_callback_at": "2026-08-06T15:30:00+05:30"
  }
}
```

No answer requires a provider receipt:

```json
{
  "event": "no_answer",
  "payload": {
    "channel": "phone",
    "contact_receipt_id": "provider-call-124"
  }
}
```

`not_interested` and `requests_human` require at least `channel`; supporting reason/context fields may also be included.

Response:

```json
{
  "id": "<ENROLLMENT_UUID>",
  "status": "running",
  "event": "connected_interested",
  "payload": {}
}
```

Raw transcripts, audio, and raw provider payloads are rejected here. Store them through the proper conversation/object-storage path and send only reference IDs plus structured facts.

### 11.3 Submit AI needs-discovery outcome

Allowed outcomes:

```text
ready_for_quote, needs_more_discovery, licensed_agent_required
```

All three require `needs_profile`, `citations`, `model_version`, and `conversation_id`:

```json
{
  "event": "ready_for_quote",
  "payload": {
    "needs_profile": {
      "product_interest": "family_health",
      "contact_consent": true,
      "family_size": 4,
      "coverage_preference": 1000000
    },
    "citations": [
      {"document_id": "<DOCUMENT_UUID>", "chunk_id": "<CHUNK_UUID>"}
    ],
    "model_version": "<MODEL_VERSION>",
    "conversation_id": "<CONVERSATION_UUID>"
  }
}
```

AI proposes this structured output. Backend code validates the event vocabulary and required fields before changing workflow state. Use `licensed_agent_required` whenever the user requests regulated advice, negotiation, or an exception.

### 11.4 Submit reviewed application/document fields

`POST /api/v1/flows/enrollments/{enrollment_id}/documents`

Current Insurance document gate requires `product_interest` and `contact_consent`. The endpoint accepts incremental non-empty fields:

```json
{
  "fields": {
    "product_interest": "family_health",
    "contact_consent": true,
    "applicant_name": "Ravi Kumar",
    "identity_document_id": "<STORED_DOCUMENT_REFERENCE>"
  }
}
```

Response:

```json
{
  "id": "<ENROLLMENT_UUID>",
  "status": "running",
  "accepted_fields": [
    "applicant_name",
    "contact_consent",
    "identity_document_id",
    "product_interest"
  ]
}
```

This prepares a case only. It does not bind coverage or issue a policy.

### 11.5 Human handoff and approval

List tenant approvals:

`GET /api/v1/flows/approvals`

Decision:

`POST /api/v1/flows/approvals/{approval_id}/decision`

```json
{
  "approved": true,
  "metadata": {
    "review_note": "Pre-screen verified; assign to licensed sales agent",
    "queue": "health-insurance-sales"
  }
}
```

Response:

```json
{
  "id": "<APPROVAL_UUID>",
  "public_id": "...",
  "status": "approved",
  "decided_at": "2026-08-05T12:30:00Z"
}
```

### 11.6 Retrieve the complete auditable case

`GET /api/v1/flows/enrollments/{root_enrollment_id}/audit`

Response sections:

```json
{
  "case": {
    "root_enrollment_id": "<UUID>",
    "public_id": "...",
    "lead_id": "<LEAD_UUID>",
    "status": "completed",
    "started_at": "...",
    "completed_at": "..."
  },
  "enrollments": [],
  "steps": [],
  "approvals": []
}
```

Each execution step contains structured `output`, `decision`, `verification`, and `audit_metadata`, together with the exact flow version and node identity.

## 12. Missing APIs required to finish the agreed product flow

These should be designed next; they do not exist as completed callable contracts today.

### 12.1 Mandatory industry selection

Preferred change: make `industry` required in `POST /api/v1/onboarding/profile`, add literal `Insurance`, and require it in both onboarding status and completion. Registration can remain account-only, provided the UI cannot continue to company upload until industry selection succeeds.

### 12.2 Manual lead-to-customer conversion

Required proposed endpoint:

`POST /api/v1/leads/{lead_id}/convert-to-customer`

Proposed request:

```json
{
  "converted_at": "2026-08-05T13:00:00Z",
  "converted_by": "human",
  "product_id": "<OPTIONAL_PRODUCT_UUID>",
  "external_customer_id": "<OPTIONAL_CRM_ID>",
  "notes": "Customer confirmed purchase with licensed agent"
}
```

The backend must ensure idempotency, create/link the canonical PostgreSQL customer, stop incompatible lead nurture, retain the original lead history, and append an audit entry.

### 12.3 Optional customer invoice entry

Required proposed endpoint:

`POST /api/v1/customers/{customer_id}/invoices`

Proposed request:

```json
{
  "external_invoice_id": "INV-2026-0012",
  "amount": 25000,
  "currency": "INR",
  "issued_at": "2026-08-05",
  "due_at": "2026-08-20",
  "status": "issued",
  "source": "manual"
}
```

Invoice input must remain optional and human-controlled. Canonical financial fields belong in PostgreSQL. A flexible copy may be projected to FerretDB for customer context; Qdrant should receive only an appropriate searchable summary, not authoritative invoice state.

## 13. Local run checklist

From the repository root:

```bash
docker compose up -d
python -m pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The document and website pipelines additionally require the indexing worker and knowledge-sync/outbox worker. Workflow progress requires the flow-execution worker. Email automation requires its mail workers and valid provider configuration.

Before frontend integration, verify:

1. `GET /` returns `{"message":"Follei API Running",...}`.
2. `GET /docs` loads the OpenAPI UI.
3. `alembic current` matches the latest head, including `20260805_tenant_hubspot_sync.py`.
4. PostgreSQL, MinIO, Kafka, FerretDB, and Qdrant are reachable.
5. A document job reaches a terminal status and storage verification reports the expected projections.
6. A HubSpot sync creates PostgreSQL CRM records and projection events.
7. No real outbound communication is activated until the tenant has reviewed its scripts, policies, and workflow.

## 14. Frontend integration rule

Use one onboarding state machine:

```text
REGISTERED
  -> PROFILE_REQUIRED
  -> INDUSTRY_SELECTED
  -> COMPANY_KNOWLEDGE_UPLOADING
  -> EXTRACTION_REVIEW
  -> CHANNELS_OPTIONAL
  -> CRM_OPTIONAL
  -> WORKFLOW_REVIEW
  -> READY
```

CRM, email, website ingestion, and invoice entry are optional setup branches. Industry selection and company profile are mandatory product requirements. Document extraction may continue asynchronously after workspace entry, but the UI must continue to show its job and review status.
