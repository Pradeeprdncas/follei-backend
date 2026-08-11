# Follei Onboarding: Registration Through Ready-for-Autonomous-Actions

This is the canonical frontend journey for a new Follei tenant. It uses only
routes confirmed current by the mounted API cleanup audit. Deprecated
compatibility routes are intentionally absent.

All authenticated calls below send:

```http
Authorization: Bearer <access_token>
```

The detailed field-by-field contracts remain in
`FRONTEND_ONBOARDING_API_REFERENCE.md`; this document explains how those
contracts form one user journey.

## 1. Choose an account path: email/password or Google

The user makes one explicit choice on the welcome screen. Preserve that choice
in frontend navigation state so the callback/resume screen knows which branch
it is completing.

### Path A — email/password

A new user submits `POST /api/v1/auth/register`. A returning user submits
`POST /api/v1/auth/login`. Registration creates both the tenant and its first
admin user and immediately returns the normal access/refresh token pair.

Advance when the response contains an `access_token`, `refresh_token`, and
`tenant_id`. A `409` during registration means the email already exists; offer
sign-in instead. A login `401` means the credentials are wrong, and `403` means
the account is inactive. Validation failures keep the user on the account form.

This path does **not** connect a knowledge source. Step 2 therefore normally
starts with `sources_connected: 0`.

### Path B — Google registration or sign-in

Submit an empty `POST /api/v1/auth/google/start` (an optional `tenant_name`
object is supported for pre-naming a new workspace). Take the
returned `authorization_url` and assign it to `window.location`; this identity
flow is a full-page redirect, not a popup.

Google returns through `GET /api/v1/auth/google/callback`, and the backend sends
the browser to the frontend's `/auth/callback` route. On success that URL has a
short-lived `exchange_code`, `expires_in=120`, `is_new_user`, `connection_id`,
`email_connection_id`, `gmail_communication=connected`, `run_id`, and
`resources=gmail,drive,calendar,contacts`. It never contains a Follei token or
Google provider token.

The frontend immediately exchanges the code through
`POST /api/v1/auth/google/exchange`. Advance only after this returns the normal
Follei access/refresh tokens and user object. The exchange code is single-use
and expires after 120 seconds; a `401` means restart the Google flow. If the
callback has `?error=access_denied` or `?error=oauth_failed`, show a safe retry
screen and do not call `/exchange`.

For a new Google identity, the callback creates the tenant and admin user. For
an existing identity, it signs that user in. In both cases it also creates a
Google Workspace knowledge connection, creates the tenant Gmail send/reply
connection, and queues independent Gmail, Drive, Calendar, and Contacts
ingestion jobs. This is the key difference in step 2: the first state response
may already contain a Google source, active run, and a usable Gmail
communication connection.

## 2. Establish the Follei session and load the first state

Store the access token, refresh token, token expiry, tenant ID, and available
user identity in session storage (or the frontend's equally short-lived secure
session store). Never place tokens in a URL. Email registration returns user and
tenant IDs directly; email login and Google exchange also return a user object.
`GET /api/v1/auth/me` can normalize the current-user view after either branch.

Immediately call `GET /api/v1/onboarding/state`. This is the only canonical
resume decision: it allows a returning user to re-enter at the right point
instead of trusting a frontend-only step counter.

- If `missing_data.profile` is non-empty, continue to profile setup.
- If the profile is complete but there are no sources, continue to source
  connection.
- If `progress.runs_active > 0`, render ingestion progress and begin polling.
- If categories or confirmations need attention, resume their review screens.
- If `can_continue` or `ready_for_autonomous_actions` is already true, restore
  the appropriate workspace experience described in step 9.

An absent or invalid bearer token returns `401`; clear the stale session or use
`POST /api/v1/auth/refresh` with the refresh token, then retry once. A state
response containing no sources after email registration is expected, not an
error. After Google sign-in, a queued source/run is expected; a failed run is a
partial onboarding state, not an authentication failure.

## 3. Capture the company profile and activate usable channels

Create the tenant profile with `POST /api/v1/onboarding/profile`. Use
`PATCH /api/v1/onboarding/profile` only when resuming or changing an existing
profile. The current readiness-mandatory fields are exactly `company_name`,
`timezone`, and `industry`. Selecting an industry also activates its workflow
pack. `lead_contact_requirement` is a tenant setting from 1 through 3 and
defaults to 1; it should still be shown during setup because it controls later
lead validation. `contact_channels` and goals may also be recorded here.

Important current-contract gap: **there is no `company_type` field in the
profile request or readiness calculation today**. Do not invent or send a
`company_type` value from this flow. If B2B/B2C becomes required, the backend
schema, persistence, state contract, and migration must be added first.

The profile's `contact_channels` are preferences, not connected providers.
Before final completion, the tenant needs at least one provider-verified active
communication channel:

- List or create a sending mailbox through `GET /api/email-connections` and
  `POST /api/email-connections`, use the Gmail connection flow at
  `POST /api/email-connections/gmail/oauth/start`, and call
  `POST /api/email-connections/{connection_id}/verify` where needed.
- List or create SMS, WhatsApp, or voice providers through
  `GET /api/channel-connections` and `POST /api/channel-connections`, retry
  provider verification through
  `POST /api/channel-connections/{connection_id}/verify`, and collect
  SMS/WhatsApp compliance through
  `POST /api/channel-connections/{connection_id}/compliance`.

These active channel records also resolve the lead-import policy: email is
always an accepted lead method; enabled, active phone/voice/SMS connections add
`phone`, and an enabled, active WhatsApp connection adds `whatsapp`.

Advance when profile creation succeeds and the chosen communication connector
reports active/verified. A duplicate profile returns `409` and should switch the
frontend to `PATCH`. Invalid industry, requirement, or conditional
`industry_other` values return `422`. Provider verification failures leave the
profile intact; show the connector error and allow retry without restarting
onboarding.

## 4. Connect one or more knowledge sources

Knowledge sources teach Follei about the tenant. They are independent of the
communication connection established in step 3.

### Google Workspace knowledge connection — popup

First call `GET /api/v1/integrations/google-workspace/connections`. A user who
chose Google identity in step 1 will usually already see the account and does
not need to reconnect it. They may still connect another account or select a
different resource set.

To connect, submit
`POST /api/v1/integrations/google-workspace/oauth/start` with some or all of
`gmail`, `drive`, `calendar`, and `contacts`. Open its `authorization_url` in a
popup. Unlike identity login, this flow intentionally remains popup-based.
Listen for a `message` from the configured frontend/backend flow and verify its
origin before trusting it:

- Success: `type: "follei:integration-connected"`, provider
  `google_workspace`, plus `connection_id` and `run_id`.
- Failure: `type: "follei:integration-error"`, provider
  `google_workspace`, and a safe `message`.

If the browser blocks the popup, ask the user to allow it and retry. Do not
advance merely because the popup closed; require the success message or confirm
the connection through
`GET /api/v1/integrations/google-workspace/connections`. A connected account
can be resynced later with
`POST /api/v1/integrations/google-workspace/connections/{connection_id}/sync`.

### Website knowledge connection — direct call

Submit `POST /api/v1/knowledge/websites/ingest` with the public URL, page limit,
optional category/engine, and `crawl_consent: true`. Ownership verification is
not required to begin crawling; consent only authorizes crawling public pages.
The response provides `source.id`, `run.id`, queued job information, and points
back to `/api/v1/onboarding/state` for status.

A `400` indicates an invalid or unsafe URL/category. A `422` means crawl consent
was absent. A `503` means the queue could not accept the job; keep the user on
the source screen and allow resubmission. Do not describe a queued source as
“knowledge ready”: connected only means the source and ingestion run now exist.

Advance to ingestion progress after at least one connection/ingest call has
created a run. Tenants may connect both source types before advancing.

## 5. Poll ingestion through the onboarding state

Poll `GET /api/v1/onboarding/state`; there is no separate canonical website
status endpoint. Use a modest backoff and ensure only one component owns the
polling timer.

Render progress from:

- `sources[]`: what is connected and each source's status.
- `runs[]`: the most recent runs, their status, counts, and stable safe error.
- `progress.runs_active`: runs currently `queued`, `running`, or `retrying`.
- `progress.categories_found` and `category_summaries[]`: usable knowledge
  appearing as ingestion completes.

Stop automatic polling when `progress.runs_active === 0`. Then route to review
even if optional categories are missing. A run with `failed` status and an
`error` is terminal for that run: show it alongside successful sources. These
are deliberately generic client messages (`Google Workspace sync failed`,
`HubSpot sync failed`, `Website ingestion failed`, or `Knowledge ingestion
failed`); detailed exceptions stay in internal PostgreSQL job/run records.
Google can be retried with the connection sync endpoint. A failed website crawl
is retried by submitting a new website ingestion request, which creates a new
run.

Do not wait for all 25 categories. Some are optional, and readiness is based on
mandatory groups rather than every individual category.

## 6. Review extracted knowledge in the mode selected by the backend

Read each entry in `category_summaries[]`. Its `display.mode` is authoritative;
the frontend must not recalculate the threshold. The backend chooses
`enumerable` at or below the configured threshold (currently 25) and
`aggregate` above it, with forced enumerable handling for accuracy-sensitive
categories such as policies/terms and pricing packages.

### Aggregate mode

Show `summary`, `display.breakdown`, and `display.sample_items`. The user's
decision is: “coverage looks representative” or “connect/resync another source
because coverage is insufficient.” There is currently no aggregate-category
approval endpoint, so do not render a fake persisted Approve button. The state
summary is deliberately bounded and never contains the full large catalog.

### Enumerable mode

Follow `display.items_endpoint`, currently
`GET /api/v1/onboarding/categories/{key}/items?page=1&page_size=25`. Show every item
through pagination and use `display.review_progress` for the overall counter.
For an item selected by ID, the current review actions are:

- Correct it: `PATCH /knowledge/review/facts/{draft_id}`.
- Approve/publish it: `POST /knowledge/review/facts/{draft_id}/approve`.
- Reject it: `POST /knowledge/review/facts/{draft_id}/reject`.

Those review bodies include the JWT tenant's `tenant_id`; the backend rejects a
cross-tenant value. Review states visible to the frontend are `pending`,
`edited`, `approved`, and `rejected`. An edited item remains a draft until it is
approved or rejected. Refresh state after mutations to update review progress.

An unknown category or item returns `404`; an already-finalized fact returns
`409`; invalid edited payloads return `422`. Keep the user's current page and
refresh the affected record instead of abandoning the review session.

Advance when the user has reviewed the coverage they care about and ingestion
is no longer active. Item-by-item completion itself is not a `can_continue`
gate; mandatory-group coverage is.

## 7. Resolve missing mandatory groups explicitly

Read `important_missing_data` and `confirmations_needed` from state. A mandatory
group is satisfied when at least one of its acceptable categories has a
`found` or `partial` status with a positive count. Missing optional categories
appear separately and require no confirmation.

For each key in `confirmations_needed`, the user either adds another source and
returns to steps 4–5, or submits `POST /api/v1/onboarding/confirmations` with one
of `provided`, `not_applicable`, `confidential`, or `continue_without`, plus an
optional note. The response is the updated full onboarding state, so use it
directly rather than immediately issuing a duplicate GET.

The decision has two different consequences:

- Any stored resolution removes that key from `confirmations_needed` and can
  allow `can_continue`.
- A confirmation does not manufacture knowledge. While the mandatory group is
  still missing, `ready_for_autonomous_actions` remains false. A
  `continue_without` resolution is additionally treated as unsafe for
  autonomous actions.

An unknown requirement returns `422`. A partially completed state simply keeps
the unresolved keys in `confirmations_needed`; remain on this step or offer
another source connection.

## 8. Optionally import leads through the reviewable CSV job

Lead import is not required to make knowledge ready, but onboarding may offer it
before entering the workspace.

For a quick client-side decision preview, submit the CSV to authenticated
`POST /api/leads/import/preview`. It returns row errors and the tenant's resolved
contactability policy without writing leads.

Create the real reviewable job with `POST /api/leads/import/upload` using
multipart `tenant_id` and `file`. The supplied tenant ID must match the bearer
token. In the currently mounted implementation, upload processing runs before
this request returns, so the normal response is already `preview_ready` or
`failed`; the persisted lifecycle still records `pending`, `parsing`,
`extracting`, and `validating`. Use `GET /api/leads/import/{job_id}` to resume or
refresh a known job. If processing is moved behind the existing worker task in
a later deployment, poll this endpoint while its status is non-terminal.

Load `GET /api/leads/import/{job_id}/preview`. Correct rows with
`PUT /api/leads/import/{job_id}/rows/{row_id}`, ignore individual rows with
`POST /api/leads/import/{job_id}/rows/{row_id}/ignore`, or use
`POST /api/leads/import/{job_id}/bulk` for supported bulk review actions.
Commit only after the user accepts the preview through
`POST /api/leads/import/{job_id}/commit`.

The batch uses partial acceptance: invalid contact rows are rejected
individually, but at least 50 accepted rows must remain. A `422` policy response
means the user must correct/add enough rows or upload another file. A `409`
preview/commit response means the job is not ready or is already in an
incompatible state. A failed job returns the stable client message `Lead import
processing failed`; its detailed exception is intentionally operator-only. A
successful commit returns counts, rejected rows, the resolved tenant policy,
and flow-enrollment status.

Advance after commit succeeds, or immediately if the user explicitly skips
lead import.

## 9. Interpret the two readiness gates and complete onboarding

Refresh `GET /api/v1/onboarding/state` and treat its flags separately:

- `can_continue` means the mandatory profile fields exist and every actually
  missing mandatory group has an explicit confirmation. It unlocks leaving the
  onboarding review and using manual workspace features. It may be true even
  though important knowledge is absent.
- `ready_for_autonomous_actions` is stricter. It requires `can_continue`, no
  mandatory group to remain missing, and no unsafe `continue_without`
  confirmation. This unlocks product controls that let Follei act without a
  human reviewing every decision.

The frontend must not equate either flag with an active communications
provider. When `can_continue` is true, call
`POST /api/v1/onboarding/complete` to finalize setup. That endpoint separately
requires the industry workflow pack and at least one provider-verified active
email, SMS, WhatsApp, or voice connection from step 3. It is idempotent and
returns `already_completed`, `completed_at`, and the still-reviewable pending
fact count.

If completion returns `422`, keep the tenant in setup and direct them to the
missing profile/industry/channel action. If completion succeeds while
`ready_for_autonomous_actions` is false, enter the manual workspace but keep
autonomous controls disabled and show what knowledge remains missing. Only
enable those controls when a fresh state response reports the stricter flag as
true.

## 10. Make the first grounded knowledge query

Once the tenant is ready, submit `POST /api/v1/knowledge/query` with a non-empty
`query`, optional taxonomy `category`, and optional `top_k` from 1 through 20.
The endpoint returns `text/event-stream`; use a streaming `fetch` reader rather
than the browser `EventSource` constructor because this is an authenticated
POST request with a JSON body.

Process events in order:

1. `sources` — render the retrieved tenant-scoped evidence and provenance.
2. Repeated `token` events — append each `text` fragment to the answer.
3. `done` — mark the answer complete.
4. `error` — stop the stream and show its safe `code`, `message`, and
   `retryable` flag.

Embedding/provider failures before streaming return a normal HTTP error with a
safe structured `detail`. Generation failures after headers are sent arrive as
an SSE `error` event. Do not blindly auto-reconnect or replay the POST, because
that can start a second generation; offer a user-controlled retry when
`retryable` is true.

The backend enforces bearer authentication and tenant-filtered retrieval. It
does not currently reject a query solely because readiness is false, so the
frontend owns the product gate: expose this first-query action only after the
latest onboarding state says `ready_for_autonomous_actions: true`.
