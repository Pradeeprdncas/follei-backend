# Mounted API Surface Audit

Audit date: 2026-08-11. Classifications below are generated and verified against
the application's OpenAPI schema, not inferred from filenames.

## Decision vocabulary

- **Keep as-is**: current onboarding or import flow depends on the endpoint.
- **Deprecate and tag**: remains mounted for compatibility, but OpenAPI marks it
  deprecated and adds `Legacy / compatibility`.
- **Keep mounted; future/unstable tag**: not part of the production onboarding
  contract. It remains callable, with `Future / unstable` visible in Swagger.
- **Unmount**: no endpoint was unmounted in this audit. Existing tests or likely
  external callers still exercise every compatibility surface identified here.

## Onboarding

The routers are complementary, not wholesale duplicates. The setup endpoints
write `OnboardingProfile`, tenant configuration, and connection readiness. The
knowledge-review endpoints read those PostgreSQL records and ingestion review
records to build the frontend state contract.

| Endpoint | Decision | Reason |
|---|---|---|
| `POST /api/v1/onboarding/profile` | Keep as-is | Creates the profile consumed by onboarding state and sets tenant lead-contact requirements. |
| `PATCH /api/v1/onboarding/profile` | Keep as-is | Updates the same authoritative setup record and selected channel preferences. |
| `PATCH /api/v1/onboarding/user-profile` | Keep as-is | Current account onboarding step for user details and terms acceptance. |
| `GET /api/v1/onboarding/status` | Deprecate and tag | Older boolean/checklist contract. `GET /state` is the canonical frontend readiness contract. Kept because compatibility tests and callers still use the communication-readiness view. |
| `GET /api/v1/onboarding/extractions` | Deprecate and tag | Older grouped draft-review response; category items plus knowledge fact review are canonical. |
| `PATCH /api/v1/onboarding/extractions/{draft_id}` | Deprecate and tag | Older edit route; the category-item/fact-review path is canonical. Kept for compatibility and existing review tests. |
| `POST /api/v1/onboarding/complete` | Keep as-is | Finalizes the profile, enforces actual communication connection readiness, and seeds onboarding context. |
| `GET /api/v1/onboarding/taxonomy` | Keep as-is | Canonical category taxonomy contract. |
| `GET /api/v1/onboarding/state` | Keep as-is | Canonical tenant-scoped onboarding/readiness response. |
| `GET /api/v1/onboarding/categories/{key}/items` | Keep as-is | Canonical paginated enumerable-review path. |
| `POST /api/v1/onboarding/confirmations` | Keep as-is | Canonical mandatory-group resolution path. |

Swagger groups the current paths under `Onboarding - setup` and
`Onboarding - knowledge review`; compatibility operations additionally appear
under `Legacy / compatibility` and carry OpenAPI `deprecated: true`.

## Lead import

The canonical workflow is `upload -> poll job -> preview/review -> commit`.

| Endpoint | Decision | Reason |
|---|---|---|
| `POST /api/leads/import` | Deprecate and tag | Direct CSV-only write bypasses the reviewable job lifecycle. |
| `POST /api/leads/import/async` | Deprecate and tag | Naming-only compatibility alias for `/upload`. |
| `POST /api/leads/import/preview` | Keep as-is | Authenticated CSV dry-run using the resolved tenant contactability policy. |
| `POST /api/leads/import/upload` | Keep as-is | Sole canonical upload entrypoint for the reviewable async job. |
| `GET /api/leads/import/{job_id}` | Keep as-is | Canonical polling endpoint. |
| `GET /api/leads/import/{job_id}/preview` | Keep as-is | Canonical job preview. |
| `PUT /api/leads/import/{job_id}/rows/{row_id}` | Keep as-is | Current per-row review/edit action. |
| `POST /api/leads/import/{job_id}/rows/{row_id}/ignore` | Keep as-is | Current per-row ignore action. |
| `POST /api/leads/import/{job_id}/bulk` | Keep as-is | Current bulk review action. |
| `POST /api/leads/import/{job_id}/commit` | Keep as-is | Canonical persistence step after review. |
| `POST /api/leads/import/{job_id}/crawl-links` | Keep as-is | Optional post-commit ingestion extension tied to the canonical job. |
| `GET /api/leads/import/{job_id}/storage-verification` | Keep as-is | Tenant-scoped diagnostic for the canonical committed job. |

## Contact-channel authority

There are three distinct concepts; treating them as one is incorrect:

1. `tenant_channel_connections`, managed by `/api/channel-connections`, is
   authoritative for active non-email lead-contact methods. Lead validation
   includes enabled rows whose status is `active`: `phone`, `voice`, or `sms`
   enables the normalized `phone` method; `whatsapp` enables `whatsapp`.
2. Email is always included in lead contactability by product policy. Lead-row
   validation therefore does **not** query `/api/email-connections` before
   accepting a valid email.
3. `tenant_email_connections`, managed by `/api/email-connections`, is
   authoritative for whether a real outbound/inbound mailbox is configured,
   enabled, verified, and active. `/onboarding/complete` and legacy `/status`
   use this table for communication readiness.

The `contact_channels` written to the onboarding profile are preferences, not
proof that a provider connection is active. Google Workspace knowledge sync is
also separate from the communications email connector.

All email-connection and channel-connection endpoints remain mounted and are
retagged under `Onboarding - email connections` and
`Onboarding - channel connections` respectively:

- `GET|POST /api/email-connections`
- `POST /api/email-connections/gmail/oauth/start`
- `GET /api/email-connections/gmail/oauth/callback`
- `PATCH|DELETE /api/email-connections/{connection_id}`
- `POST /api/email-connections/{connection_id}/verify`
- `GET|POST /api/channel-connections`
- `POST /api/channel-connections/{connection_id}/verify`
- `POST /api/channel-connections/{connection_id}/compliance`

## Mounted future/unstable domains

Every operation below stays mounted but now carries the `Future / unstable`
OpenAPI tag in addition to its domain tag.

### Agents

- `POST|GET /api/v1/agents`
- `GET|PATCH|DELETE /api/v1/agents/{agent_id}`
- `POST /api/v1/agents/{agent_id}/chat`
- `POST|GET /api/v1/agents/{agent_id}/versions`
- `POST|GET /api/v1/agents/{agent_id}/sessions`
- `PATCH /api/v1/agents/{agent_id}/sessions/{session_id}`
- `POST|GET /api/v1/agents/{agent_id}/tasks`
- `PATCH /api/v1/agent-tasks/{task_id}`
- `POST|GET /api/v1/agents/{agent_id}/memories`
- `POST|GET /api/v1/agents/{agent_id}/feedback`
- `POST|GET /api/v1/agents/{agent_id}/tool-permissions`

### CRM / HubSpot

- `POST /api/v1/crm/hubspot/oauth/start`
- `GET /api/v1/crm/hubspot/oauth/callback`
- `GET /api/v1/crm/connections`
- `POST /api/v1/crm/hubspot/connections` (already deprecated)
- `DELETE /api/v1/crm/hubspot/connections`
- `POST /api/v1/crm/hubspot/sync`
- `GET /api/v1/crm/records`
- `GET /api/v1/crm/sync-runs`

### Campaigns

- `POST|GET /api/v1/campaigns`
- `GET|PUT|DELETE /api/v1/campaigns/{campaign_id}`
- `POST /api/v1/campaigns/{campaign_id}/start`
- `POST /api/v1/campaigns/{campaign_id}/schedule`
- `POST /api/v1/campaigns/{campaign_id}/pause`
- `POST /api/v1/campaigns/{campaign_id}/cancel`
- `GET /api/v1/campaigns/{campaign_id}/stats`
- `GET /api/v1/campaigns/{campaign_id}/analytics`
- `POST|DELETE /api/v1/campaigns/{campaign_id}/leads/{lead_id}`
- `GET /api/v1/campaigns/{campaign_id}/leads`
- `GET /api/v1/campaigns/{campaign_id}/track/open`
- `GET /api/v1/campaigns/{campaign_id}/track/click`
- `POST /api/v1/campaigns/{campaign_id}/track/delivery`
- `POST /api/v1/campaigns/{campaign_id}/track/bounce`

### Customers and renewals

- `POST|GET /api/customers`
- `GET|PATCH|DELETE /api/customers/{customer_id}`
- `POST|GET /api/customers/{customer_id}/contacts`
- `POST|GET /api/customers/{customer_id}/health-scores`
- `POST|GET /api/customers/{customer_id}/events`
- `POST|GET /api/customers/{customer_id}/renewals`
- `PATCH /api/renewals/{renewal_id}`

### Opportunities and meetings

- `POST|GET /api/opportunities`
- `GET|PATCH /api/opportunities/{opportunity_id}`
- `POST /api/opportunities/{opportunity_id}/proposals`
- `POST /api/opportunities/{opportunity_id}/quotes`
- `POST|GET /api/meetings`
- `PATCH|DELETE /api/meetings/{meeting_id}`

### Tools / MCP registry

- `POST|GET /api/tools`
- `GET /api/tools/{tool_id}`
- `POST /api/tools/{tool_id}/execute`
- `POST /api/tools/{tool_id}/permissions`
- `GET /api/tool-executions`
- `GET /api/connector-logs`

## Verification

- OpenAPI classification contract: PASS (`2 passed`).
- Required onboarding/profile/completion/extraction and tenant contact-policy
  regressions: PASS. The PostgreSQL state contract, tenant-isolation,
  pagination, and 8,001-item performance gates were then run separately
  against the live local PostgreSQL service: PASS (`4 passed`, no skips).
- No current onboarding dependency was unmounted.
