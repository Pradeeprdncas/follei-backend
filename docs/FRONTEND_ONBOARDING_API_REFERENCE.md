# Follei frontend onboarding API reference

This document describes the contracts mounted by the current Follei backend. It is intended to be sufficient for a frontend implementation without reading Python code.

> Contract snapshot: 2026-08-10 working tree, including public Google registration/sign-in plus automatic Workspace sync. Paths and field names below were checked against the mounted FastAPI application and its Pydantic models.

## 0. Conventions used by every section

### Base URL and content types

Examples assume an API origin of `http://localhost:8000`. Prefix relative paths with the environment's API origin.

- JSON requests: `Content-Type: application/json`
- File uploads: `multipart/form-data`; let the browser set the boundary.
- Knowledge answers: `text/event-stream`
- Public Google auth callback: `302 Found` redirect to the frontend.
- Authenticated Workspace OAuth callback: `text/html`; it remains a popup `postMessage` flow.

### Authentication

Except where an endpoint is explicitly public, send:

```http
Authorization: Bearer <access_token>
```

The signed access token carries both the user ID (`sub`) and tenant ID (`tenant_id`). Tenant-scoped endpoints derive tenancy from that claim. Never let a user type or select a tenant ID. The legacy lead upload and fact-review bodies still contain a `tenant_id`; when required, it must be copied from the authenticated session and the server rejects a mismatch.

Shared authentication failures are:

| Status | Body | Cause |
|---|---|---|
| `401` | `{"detail":"Missing bearer token"}` | No `Authorization: Bearer …` header. |
| `401` | `{"detail":"Invalid token"}` | Bad signature, malformed JWT, expired token, or missing/invalid UUID claims. |

Registration and login return `expires_in: 3600`. Refresh is currently also a signed JWT with the same default lifetime, not a long-lived opaque token. Refresh before expiry; if both tokens expire, send the user to sign-in.

```http
POST /api/v1/auth/refresh
Content-Type: application/json

{"refresh_token":"<refresh-token>"}
```

Success is `200 {"access_token":"<jwt>","expires_in":3600}`. An invalid or expired refresh token is `401 {"detail":"Invalid refresh token"}`. The endpoint does not rotate or return a new refresh token.

### JSON envelope

New onboarding/integration endpoints return this envelope:

```json
{
  "data": {},
  "meta": {
    "request_id": "54ccbd62-9d2e-4c27-a616-f86ecad0e973",
    "generated_at": "2026-08-10T10:30:12.422108+00:00"
  },
  "errors": []
}
```

`data` is the endpoint-specific result. `meta.request_id` is a per-response support/debug identifier; `meta.generated_at` is an ISO-8601 UTC timestamp. Accepted async work also adds `meta.accepted: true`. `errors` is currently an empty array on successful responses. Auth and lead-import endpoints do **not** consistently use this envelope.

### Error body shapes

Three error shapes occur:

```json
{"detail":"Human-readable error"}
```

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "field_name"],
      "msg": "Field required",
      "input": {}
    }
  ]
}
```

```json
{
  "detail": {
    "code": "machine_readable_code",
    "message": "Optional public message",
    "retryable": true
  }
}
```

The second shape is FastAPI/Pydantic `422` validation output. The entries can also use `query`, `path`, or `body` in `loc`. Unhandled infrastructure/database failures return `500`; in production treat its body as opaque and show a generic retry/support message. Network failures and browser cancellations have no HTTP response.

---

## 1. Registration — email and password

### Method, path, auth, and sequence

`POST /api/v1/auth/register` — public; do not send a bearer token.

Call this after the user submits the create-account form. Store the returned access/refresh tokens and tenant/user IDs. Then continue to workspace/company profile setup, connectors, and `GET /api/v1/onboarding/state`.

### Request body

Unknown fields are rejected.

| Field | Required | Type and validation | Example | Meaning |
|---|---:|---|---|---|
| `email` | yes | valid email | `maya@northstar.example` | Follei login identity. |
| `password` | yes | string, 8–128 chars, at least one ASCII letter and one digit | `Orbit2026!` | Account password. |
| `full_name` | yes | string, 1–200 chars | `Maya Chen` | User display name. |
| `tenant_name` | yes | string, 1–200 chars | `Northstar Labs` | Workspace/tenant name. |

```json
{
  "email": "maya@northstar.example",
  "password": "Orbit2026!",
  "full_name": "Maya Chen",
  "tenant_name": "Northstar Labs"
}
```

### Success response

`201 Created`

```json
{
  "user_id": "6955785b-235b-47fb-a924-11268d26c939",
  "tenant_id": "62164916-2780-4478-968f-e74c3bd34a58",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9…",
  "token_type": "bearer",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9…",
  "expires_in": 3600
}
```

All fields are required. `user_id` and `tenant_id` are UUID strings. `access_token` authenticates API calls; `refresh_token` is accepted by the refresh endpoint; `token_type` is currently always `bearer`; `expires_in` is seconds.

### Errors

| Status | Body/cause |
|---|---|
| `409` | `{"detail":"User email already exists"}` when the login email is registered. |
| `422` | Validation array for email/password/name limits, password complexity, missing fields, or any unknown field. |
| `500` | Tenant/user/default-workflow persistence failure. Treat body as opaque. |

### Frontend handling notes

- Registration is account creation only. Connect Google, Gmail, or another provider through its dedicated OAuth/integration endpoint after registration.
- Registration does not currently perform email-code verification.

---

## 2. Sign-in — email and password

### Method, path, auth, and sequence

`POST /api/v1/auth/login` — public.

Call for an existing user. Store tokens and `user`; then load `GET /api/v1/onboarding/state`. If `can_continue` is false, resume onboarding; otherwise route to the normal workspace.

### Request body

| Field | Required | Type and validation | Example |
|---|---:|---|---|
| `email` | yes | valid email | `maya@northstar.example` |
| `password` | yes | string | `Orbit2026!` |

Extra fields are currently accepted and ignored; do not rely on that.

```json
{"email":"maya@northstar.example","password":"Orbit2026!"}
```

### Success response

`200 OK`

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "6955785b-235b-47fb-a924-11268d26c939",
    "email": "maya@northstar.example",
    "full_name": "Maya Chen",
    "tenant_id": "62164916-2780-4478-968f-e74c3bd34a58",
    "roles": ["admin"]
  }
}
```

Token fields have the meanings described in registration. `user.id` and `user.tenant_id` are UUID strings; `roles` is an array of role-name strings and can be empty.

### Errors

| Status | Body/cause |
|---|---|
| `401` | `{"detail":"Invalid email or password"}` for either an unknown email or wrong password. Do not reveal which. |
| `403` | `{"detail":"User is inactive"}` when the account is disabled. |
| `422` | Validation array when email/password is missing or email syntax is invalid. |
| `500` | Database/auth persistence failure. |

### Frontend handling notes

- Keep access tokens in memory where possible. If durable storage is required, account for XSS risk.
- Refresh shortly before 3600 seconds. A refresh after its own expiry fails and requires sign-in.
- On any protected endpoint's `401`, attempt refresh once; prevent parallel refresh storms with a single shared promise.

---

## 3. Google OAuth registration/sign-in with automatic Workspace connection

This public flow handles both new and returning users. It verifies the Google identity, creates a Follei tenant/user when the email is new, connects that same Google account as a Workspace knowledge source, creates the tenant Gmail send/reply connection, and queues independent Gmail, Drive, Calendar, and Contacts sync jobs. Provider access and refresh tokens remain encrypted server-side.

This is deliberately a combined identity-and-data-consent flow, not identity-only OAuth. The Google consent screen asks for `openid`, `email`, `profile`, read access to all four Workspace resources, and Gmail communication access for sending, replying, and inbound auto-reply tracking.

### 3.1 Start Google registration/sign-in

`POST /api/v1/auth/google/start` — public; do not send a bearer token.

The request body is optional. The recommended sign-in/sign-up call sends no
body at all. `{}` and an optional `tenant_name` object are also accepted.

| Field | Required | Type/validation | Example | Meaning |
|---|---:|---|---|---|
| `tenant_name` | no | string or `null`, 1–200 chars when present | `Northstar Labs` | Name for a newly created Follei workspace. Ignored for an existing Google/Follei user. If omitted for a new user, the backend derives it from Google's hosted domain or display name. |

Unknown fields are rejected.

```ts
const response = await fetch(`${API_ORIGIN}/api/v1/auth/google/start`, {
  method: 'POST'
});
```

`200 OK`:

```json
{
  "data": {
    "flow": "account_auth",
    "requires_bearer": false,
    "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=…&state=…&nonce=…&code_challenge=…",
    "resources": ["gmail", "drive", "calendar", "contacts"],
    "scopes": [
      "https://www.googleapis.com/auth/gmail.readonly",
      "https://www.googleapis.com/auth/drive.readonly",
      "https://www.googleapis.com/auth/calendar.readonly",
      "https://www.googleapis.com/auth/contacts.readonly",
      "https://www.googleapis.com/auth/gmail.modify",
      "https://www.googleapis.com/auth/gmail.send"
    ],
    "gmail_communication": {
      "requested": true,
      "capabilities": ["send", "reply", "read_inbound"]
    }
  },
  "meta": {"request_id":"<uuid>","generated_at":"<ISO-8601>"},
  "errors": []
}
```

`flow=account_auth` and `requires_bearer=false` distinguish this endpoint from
the authenticated, mid-onboarding connector. `resources` is always all four
values for this flow. `authorization_url` includes one-time state, nonce, PKCE,
offline access, and `prompt=consent`. `scopes` lists the Workspace and Gmail
communication scopes; the URL additionally contains Google's identity scopes.

Errors:

| Status | Body/cause |
|---|---|
| `422` | `{"detail":"Google OAuth client ID/secret are not configured"}` when backend Google credentials are absent. |
| `422` | Standard validation array for a malformed/too-long tenant name or unknown field. An absent body is valid. |
| `500` | OAuth-state persistence failure. |

After receiving `authorization_url`, navigate the current page with `window.location.assign(authorization_url)`. Do not open a popup and do not install a `message` listener for this public authentication flow. If navigation cannot happen immediately, render a normal link to the returned Google URL.

### 3.2 Google auth callback and full-page frontend redirect

`GET /api/v1/auth/google/callback` — public provider callback. The frontend does not call it. Register the backend's configured `GOOGLE_AUTH_OAUTH_REDIRECT_URI` exactly in Google Cloud.

Accepted query fields are `state?: string`, `code?: string`, and `error?: string`. All are optional at HTTP validation level so cancellation can still redirect safely. Success requires valid, unexpired, single-use `state` and `code`, and no `error`.

The callback returns `302 Found` with a `Location` under the configured frontend base URL. It never returns a popup script.

Success:

```http
HTTP/1.1 302 Found
Location: https://app.follei.example/auth/callback?exchange_code=QF98vS…&expires_in=120&is_new_user=true&connection_id=167f9aed-22b7-4de8-b062-a69687f94c77&email_connection_id=32afcc62-9ec7-41a9-8c55-332098a81d5f&gmail_communication=connected&run_id=80cb66ce-0137-4548-9b8f-45d4a77a50a0&resources=gmail%2Cdrive%2Ccalendar%2Ccontacts
```

Query fields are all strings. `exchange_code` is a one-use credential valid for 120 seconds; exchange it immediately and never log/store it. `expires_in` is `"120"`. `is_new_user` is `"true"` or `"false"`. `connection_id` is the created/reused Workspace knowledge connection. `email_connection_id` is the created/reused tenant Gmail communication connection. `gmail_communication=connected` means backend-side sending, replies, campaigns, and inbound auto-reply tracking were authorized. `run_id` identifies the ingestion run, which already contains four independently queued jobs. `resources` is one comma-separated value: `gmail,drive,calendar,contacts`.

Failure, including user cancellation:

```http
HTTP/1.1 302 Found
Location: https://app.follei.example/auth/callback?error=access_denied
```

User cancellation or Google's `access_denied` becomes the fixed safe value `error=access_denied`. Every other failure becomes `error=oauth_failed`, including bad/expired/reused state, provider exchange/identity verification failure, inactive Follei user, missing refresh token, or account/connector persistence failure. Queue publication happens after the redirect and cannot fail authentication. Raw provider error descriptions are discarded. The redirect never contains Google tokens, client secrets, provider authorization codes, or raw provider errors.

Failure redirects also include a safe `step` value so the frontend can show a
useful retry message and support can locate the server-side log. Its enum is
`authorization`, `token_exchange`, `account_setup`, `workspace_connection`,
`gmail_connection`, or `session_exchange`. It never contains provider data.

The frontend route `/auth/callback` should read `window.location.search`:

1. If `error` exists, show a safe retry/cancelled state and do not call exchange.
2. If `exchange_code` exists, remove or replace the URL immediately so browser history, screenshots, and analytics do not retain it.
3. Call `/api/v1/auth/google/exchange` with that code.
4. Store the returned Follei session, then use `is_new_user` to select onboarding versus the existing workspace.
5. Retain `connection_id`, `email_connection_id`, `gmail_communication`, `run_id`, and split `resources` on commas if the UI needs sync progress.

### 3.3 Exchange redirect code for Follei session

`POST /api/v1/auth/google/exchange` — public.

| Field | Required | Type/validation | Example |
|---|---:|---|---|
| `exchange_code` | yes | string, 20–512 chars | the exact `exchange_code` query value from `/auth/callback` |

Unknown fields are rejected.

```json
{"exchange_code":"QF98vS…short-lived-one-time-code…"}
```

`200 OK` returns the Follei session plus the safe account/connector/ingestion
handoff. Provider tokens and Google authorization codes are never returned:

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "6955785b-235b-47fb-a924-11268d26c939",
    "email": "maya@northstar.example",
    "full_name": "Maya Chen",
    "tenant_id": "62164916-2780-4478-968f-e74c3bd34a58",
    "roles": ["admin"]
  },
  "account": {
    "is_new_user": true,
    "action": "created"
  },
  "google_workspace": {
    "connection_id": "167f9aed-22b7-4de8-b062-a69687f94c77",
    "email_address": "maya@northstar.example",
    "status": "active",
    "resources": ["gmail", "drive", "calendar", "contacts"]
  },
  "gmail_communication": {
    "connection_id": "32afcc62-9ec7-41a9-8c55-332098a81d5f",
    "status": "active",
    "capabilities": ["send", "reply", "read_inbound"]
  },
  "ingestion": {
    "run_id": "80cb66ce-0137-4548-9b8f-45d4a77a50a0",
    "status": "queued",
    "state_endpoint": "/api/v1/onboarding/state"
  }
}
```

Session fields have the meaning documented in section 2. `account.action` is
`created` for a newly provisioned tenant/user and `signed_in` for an existing
email. The connection objects identify the server-side records; their status
does not expose credentials. Ingestion is asynchronous: poll the authenticated
`state_endpoint` with the returned bearer token to receive extracted,
structured category summaries as each resource finishes. The exchange
atomically marks the code consumed and updates `last_login_at`.

Errors:

| Status | Body/cause |
|---|---|
| `401` | `{"detail":"Invalid or expired Google exchange code"}` for unknown, expired, or already-used code. |
| `403` | `{"detail":"User is inactive"}` if the user became inactive between callback and exchange. |
| `422` | Validation array for a missing, too-short/long, non-string, or extra field. |
| `500` | Exchange/session persistence failure. |

Sequence: start → full-page Google navigation → backend 302 to `/auth/callback` → read/remove query parameters → exchange immediately → store Follei tokens → call onboarding state. For a new user, continue profile onboarding while the four Google jobs run. For an existing user, restore the normal workspace and poll the returned `run_id` as needed.

---

## 4. Google Workspace OAuth connection

This connection imports four independently queued resources: `gmail`, `drive`, `calendar`, and `contacts`. It is tenant-scoped and is only available after Follei authentication.

> Unlike public Google registration/sign-in in section 3, this mid-onboarding connection intentionally remains a popup with `window.opener.postMessage`. Do not full-page navigate away from an authenticated onboarding session for this flow.

### 4.1 Start Workspace OAuth

`POST /api/v1/integrations/google-workspace/oauth/start` — bearer auth required.

#### Request body

The JSON body itself is required; `{}` selects all resources.

| Field | Required | Type and validation | Example |
|---|---:|---|---|
| `resources` | no | array of strings; default all four; each must be `gmail`, `drive`, `calendar`, or `contacts`; at least one after de-duplication | `["gmail","drive"]` |

```json
{"resources":["gmail","drive","calendar","contacts"]}
```

#### Success response

`200 OK`

```json
{
  "data": {
    "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=…&state=…&nonce=…&code_challenge=…",
    "resources": ["gmail", "drive", "calendar", "contacts"],
    "scopes": [
      "https://www.googleapis.com/auth/gmail.readonly",
      "https://www.googleapis.com/auth/drive.readonly",
      "https://www.googleapis.com/auth/calendar.readonly",
      "https://www.googleapis.com/auth/contacts.readonly"
    ]
  },
  "meta": {"request_id":"<uuid>","generated_at":"<ISO-8601>"},
  "errors": []
}
```

`authorization_url` contains one-time state, nonce, and PKCE values and requests consent. `resources` is the requested list; `scopes` maps each resource to its Google read-only scope. Do not inspect or persist OAuth state yourself.

#### Errors

| Status | Body/cause |
|---|---|
| `401` | Shared missing/invalid bearer error. |
| `422` | `{"detail":"Invalid Google resources: ['bad']"}` for unsupported values. |
| `422` | `{"detail":"Invalid Google resources: none selected"}` for an empty list. |
| `422` | `{"detail":"Google OAuth client ID/secret are not configured"}` when server configuration is incomplete. |
| `422` | Standard validation array if body is absent or `resources` is not an array of strings. |
| `500` | Unexpected DB/state-generation failure. |

#### Sequence and popup handling

1. User clicks Connect.
2. **Synchronously** call `window.open('about:blank', ...)` in the click handler. If it returns `null`, show “Allow popups and try again.” This avoids popup blockers while the `fetch` runs.
3. `POST` this endpoint with the bearer header.
4. Set `popup.location.href = response.data.authorization_url`.
5. Listen for the callback `postMessage` described below.
6. On success, refresh the connections list and poll onboarding state using the returned `run_id`.

### 4.2 Google callback and `postMessage`

`GET /api/v1/integrations/google-workspace/oauth/callback?state=<state>&code=<code>` — public callback; Google navigates the popup here. Do not call it from application JavaScript and do not attach a bearer token.

#### Query schema

| Field | Required | Type | Meaning |
|---|---:|---|---|
| `state` | yes | string | One-time state generated by the start endpoint; expires after approximately 10 minutes and cannot be reused. |
| `code` | yes | string | Google authorization code. |

#### HTTP response and success message

The callback returns `200 text/html`, not JSON. Its script posts to `window.opener` using the configured frontend origin:

```json
{
  "type": "follei:integration-connected",
  "provider": "google_workspace",
  "connection_id": "167f9aed-22b7-4de8-b062-a69687f94c77",
  "run_id": "80cb66ce-0137-4548-9b8f-45d4a77a50a0"
}
```

`connection_id` identifies the tenant connection. `run_id` identifies the initial ingestion run; the backend has queued one independent job per selected resource before emitting success.

#### Failure message

Failures caught inside the callback still return `200 text/html` and post this deliberately non-sensitive shape:

```json
{
  "type": "follei:integration-error",
  "provider": "google_workspace",
  "message": "Connection could not be completed"
}
```

It is emitted for expired/reused/bad state, token exchange failure, missing refresh token, unverified/mismatched Google identity, connection persistence failure, or initial queue failure. No OAuth tokens or provider response bodies are exposed.

#### Callback edge-case errors

| Status | Body/cause |
|---|---|
| `422` | Standard validation JSON if Google returns without required `state` or `code`—notably some user-denial/cancellation redirects. In this path the HTML script does not run and there is no failure `postMessage`. |
| `200` | HTML plus the generic failure message for callback errors caught after query validation. |

#### Safe message listener

```ts
const API_ORIGIN = new URL(import.meta.env.VITE_API_URL).origin;

function waitForGoogleWorkspacePopup(popup: Window): Promise<
  | { type: 'follei:integration-connected'; provider: 'google_workspace'; connection_id: string; run_id: string }
  | { type: 'follei:integration-error'; provider: 'google_workspace'; message: string }
> {
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => cleanup(new Error('Google connection timed out')), 10 * 60_000);
    const closed = window.setInterval(() => {
      if (popup.closed) cleanup(new Error('Google window closed before completion'));
    }, 500);

    const onMessage = (event: MessageEvent) => {
      if (event.origin !== API_ORIGIN || event.source !== popup) return;
      const value = event.data;
      if (!value || value.provider !== 'google_workspace') return;
      if (value.type !== 'follei:integration-connected' && value.type !== 'follei:integration-error') return;
      window.removeEventListener('message', onMessage);
      window.clearTimeout(timeout);
      window.clearInterval(closed);
      popup.close();
      resolve(value);
    };

    const cleanup = (error: Error) => {
      window.removeEventListener('message', onMessage);
      window.clearTimeout(timeout);
      window.clearInterval(closed);
      if (!popup.closed) popup.close();
      reject(error);
    };
    window.addEventListener('message', onMessage);
  });
}
```

Do not accept messages solely by `type`; validate `event.origin`, `event.source`, and `provider`. Treat popup closure/timeout as cancellation because the missing-`code` 422 case cannot post a message.

### 4.3 List Workspace connections

`GET /api/v1/integrations/google-workspace/connections` — bearer auth required. No body or query parameters.

Call after callback success and whenever rendering integration settings. After it, either trigger a sync or proceed to another connector/onboarding state.

#### Success response

`200 OK`

```json
{
  "data": {
    "connections": [
      {
        "id": "167f9aed-22b7-4de8-b062-a69687f94c77",
        "email": "maya@northstar.example",
        "status": "active",
        "resources": ["gmail", "drive", "calendar", "contacts"],
        "last_synced_at": "2026-08-10T10:35:42.003112",
        "last_error": null
      }
    ]
  },
  "meta": {"request_id":"<uuid>","generated_at":"<ISO-8601>"},
  "errors": []
}
```

`connections` can be empty. `id` is the connection UUID; `email` is the verified Google account; `status` is persisted connection state (normally `active`); `resources` contains enabled resource enum values; `last_synced_at` is ISO-8601 or `null`; `last_error` is a safe status string or `null`. Tokens/secrets are never returned.

#### Errors

`401` shared auth errors; `500` database failure. There is no `404` for an empty list.

### 4.4 Trigger a Workspace sync

`POST /api/v1/integrations/google-workspace/connections/{connection_id}/sync` — bearer auth required.

#### Request

`connection_id` is a UUID path value returned by list/callback. The JSON body is required; `{}` syncs all resources enabled on the connection.

| Field | Required | Type and validation | Example |
|---|---:|---|---|
| `resources` | no | array of `gmail`, `drive`, `calendar`, `contacts`, or `null`; when omitted/null, uses enabled resources; result must be non-empty | `["drive"]` |

#### Success response

`202 Accepted`

```json
{
  "data": {
    "connection_id": "167f9aed-22b7-4de8-b062-a69687f94c77",
    "run_id": "80cb66ce-0137-4548-9b8f-45d4a77a50a0",
    "status": "queued",
    "jobs": [
      {"id":"d7603cef-3376-492f-8b8e-c05e20642bca","type":"google_gmail_sync","status":"queued"},
      {"id":"7ba76a08-917d-4a85-a34b-3cc5e5429ba6","type":"google_drive_sync","status":"queued"}
    ]
  },
  "meta": {"request_id":"<uuid>","generated_at":"<ISO-8601>","accepted":true},
  "errors": []
}
```

Each `jobs[]` item is independently retryable server-side. `type` is exactly `google_gmail_sync`, `google_drive_sync`, `google_calendar_sync`, or `google_contacts_sync`. Poll onboarding state and match `runs[].id` to `run_id`; refresh connections to obtain last sync/error summary.

#### Errors

| Status | Body/cause |
|---|---|
| `401` | Shared auth error. |
| `404` | `{"detail":"Google Workspace connection not found"}` for an unknown, inactive, or other-tenant connection. |
| `409` | `{"detail":"Google Workspace knowledge source is missing; reconnect the account"}`. |
| `422` | Invalid UUID path, malformed JSON/resources, unsupported resource, or no selected/enabled resources. Unsupported values use `{"detail":"Invalid Google resources: [...]"}`. |
| `503` | `{"detail":"Google Workspace sync could not be queued"}` for broker/queue failure. |
| `500` | Unexpected database failure. |

---

## 5. Website connector

### 5.1 List available crawl engines

`GET /api/v1/knowledge/websites/engines` — currently public; no auth header, body, or query fields.

Call before showing engine choices. A normal UI should choose `auto` and need not expose engines.

```json
{
  "data": {
    "engines": [
      {"engine":"aiohttp","installed":true},
      {"engine":"crawl4ai","installed":true},
      {"engine":"scrapy","installed":false}
    ]
  },
  "meta": {"request_id":"<uuid>","generated_at":"<ISO-8601>"},
  "errors": []
}
```

`engine` is one of `aiohttp`, `crawl4ai`, `scrapy`; `installed` tells whether that adapter is usable by this deployment. Errors are limited to `500` if engine inspection fails.

### 5.2 Add a website source

`POST /api/v1/knowledge/websites/ingest` — bearer auth required.

#### Request body

| Field | Required | Type and validation | Example | Meaning |
|---|---:|---|---|---|
| `url` | yes | valid HTTP/HTTPS URL; no embedded credentials; host must resolve only to public IPs | `https://northstar.example/` | Crawl root. |
| `max_pages` | no | integer 1–25, default `10` | `10` | Maximum pages queued for this source. |
| `category` | no | string or `null`; must normalize to a supported taxonomy key/alias | `products` | Optional category hint. |
| `engine` | no | enum `auto`, `aiohttp`, `crawl4ai`, `scrapy`; default `auto` | `auto` | Crawl adapter preference. |
| `crawl_consent` | yes | boolean; must be `true` | `true` | Consent to crawl public pages. It is **not** proof of website ownership. |

The backward-compatible request alias `confirm_authorized` is also accepted in place of `crawl_consent`; new clients should use `crawl_consent`.

```json
{
  "url": "https://northstar.example/",
  "max_pages": 10,
  "category": "products",
  "engine": "auto",
  "crawl_consent": true
}
```

#### Success response

`202 Accepted`

```json
{
  "data": {
    "source": {
      "id": "862637ad-b0fc-49ab-b0cf-c66eaf93a33e",
      "type": "website",
      "status": "queued",
      "crawl_consent": true,
      "ownership_verification": "unverified"
    },
    "run": {"id":"08fa6706-e3a7-488f-a438-fce11cb207a8","status":"queued"},
    "jobs": [
      {"id":"5e599e16-7b64-47a4-badc-cac28ab020b4","type":"website_crawl","status":"queued"}
    ],
    "status_url": "/api/v1/onboarding/state"
  },
  "meta": {"request_id":"<uuid>","generated_at":"<ISO-8601>","accepted":true},
  "errors": []
}
```

`source.id` identifies the tenant knowledge source. `run.id` is the polling correlation ID. `jobs` is the queued worker work. `ownership_verification` remains `unverified`; ownership verification is intentionally separate and is not required to crawl public content. `status_url` is relative to the API origin.

#### Errors

| Status | Body/cause |
|---|---|
| `400` | `{"detail":"Only public HTTP(S) URLs without embedded credentials are allowed"}` for unsafe scheme/credentials. |
| `400` | `{"detail":"Website host did not resolve"}` or `{"detail":"Website host resolves to a private or non-public address"}` for SSRF checks. |
| `400` | `{"detail":"Unsupported knowledge category: <value>"}` for a bad category. |
| `401` | Shared auth error. |
| `422` | `{"detail":"Crawl consent must be confirmed"}` when false. |
| `422` | Validation array for missing/invalid URL, consent, page range, or engine enum. |
| `503` | `{"detail":"Website ingestion could not be queued"}`; the created source/run/job are marked failed. |
| `500` | Unexpected DNS resolver, database, or infrastructure failure. |

Explicitly selecting an engine that is not installed may be accepted by this endpoint and fail later in the worker. Check `/engines` first or use `auto`.

### 5.3 Check website ingestion status

There is no dedicated `GET /websites/{source_id}` route. Poll `GET /api/v1/onboarding/state`, find `sources[].id === source.id`, and find `runs[].id === run.id`.

Poll every 1–2 seconds initially, back off to 5–10 seconds, pause when the tab is hidden, and stop when the matching run leaves `queued`, `running`, or `retrying`. A failed run exposes `runs[].error`. The state returns only the 20 newest runs, so retain the returned IDs and do not poll indefinitely.

---

## 6. Onboarding state

### Method, path, auth, and sequence

`GET /api/v1/onboarding/state` — bearer auth required; no body or query parameters.

Call after login, after creating/connecting any source, while polling ingestion, after item review, and after a confirmation. This endpoint reads the PostgreSQL control plane only; it does not perform live FerretDB or Qdrant searches.

### Full success response

`200 OK`

```json
{
  "data": {
    "step": "knowledge_review",
    "progress": {
      "profile_complete": true,
      "sources_connected": 2,
      "runs_active": 1,
      "categories_found": 6,
      "categories_total": 25
    },
    "sources": [
      {
        "id": "862637ad-b0fc-49ab-b0cf-c66eaf93a33e",
        "name": "Website: northstar.example",
        "type": "website",
        "status": "processing",
        "config": {"url":"https://northstar.example/","engine":"auto","max_pages":10,"category":"products","crawl_consent":true,"ownership_verification":"unverified"}
      }
    ],
    "runs": [
      {
        "id": "08fa6706-e3a7-488f-a438-fce11cb207a8",
        "source_id": "862637ad-b0fc-49ab-b0cf-c66eaf93a33e",
        "status": "running",
        "page_count": 4,
        "document_count": 1,
        "error": null
      }
    ],
    "category_summaries": [
      {
        "key": "products",
        "label": "Products",
        "category_group": "business",
        "mandatory_group": "business_fundamentals",
        "status": "found",
        "count": 8412,
        "summary": "8,412 products across six main catalog groups.",
        "confidence": 0.85,
        "needs_review": false,
        "display": {
          "mode": "aggregate",
          "breakdown": [{"label":"Electronics","count":3100}],
          "sample_items": ["USB-C Hub 7-in-1", "Wireless Mouse M2"]
        }
      },
      {
        "key": "pricing_packages",
        "label": "Pricing & Packages",
        "category_group": "business",
        "mandatory_group": "business_fundamentals",
        "status": "found",
        "count": 3,
        "summary": "Three published packages.",
        "confidence": 0.94,
        "needs_review": true,
        "display": {
          "mode": "enumerable",
          "items_endpoint": "/api/v1/onboarding/categories/pricing_packages/items",
          "review_progress": {"reviewed":1,"total":3}
        }
      }
    ],
    "missing_data": {
      "profile": [],
      "optional": ["faqs", "communication_preferences", "follow_up_patterns"]
    },
    "important_missing_data": [
      {"requirement":"governance","acceptable_categories":["policies_terms"]}
    ],
    "confirmations_needed": ["governance"],
    "confirmations": [],
    "can_continue": false,
    "ready_for_autonomous_actions": false
  },
  "meta": {"request_id":"<uuid>","generated_at":"<ISO-8601>"},
  "errors": []
}
```

The actual response always contains **all 25** category summary objects; the example is shortened.

### Field reference

| Field | Type | Meaning |
|---|---|---|
| `step` | string, currently `knowledge_review` | Current aggregate onboarding stage. |
| `progress.profile_complete` | boolean | All of `company_name`, `timezone`, and `industry` exist. |
| `progress.sources_connected` | integer | Number of tenant knowledge-source records, regardless of terminal status. |
| `progress.runs_active` | integer | Runs whose status is `queued`, `running`, or `retrying`. |
| `progress.categories_found` | integer | Categories with status exactly `found`; `partial` is not counted here. |
| `progress.categories_total` | integer, currently `25` | Canonical base taxonomy size. |
| `sources[]` | array | Tenant sources ordered oldest first. |
| `sources[].id` | UUID string | Source identifier. |
| `sources[].name` | string | Display name. |
| `sources[].type` | string | Provider/source type such as `website` or `google_workspace`. |
| `sources[].status` | string | Current persisted source state. UI should at least handle `queued`, `running`/`processing`, `retrying`, `active`/`completed`, and `failed`. |
| `sources[].config` | object | Provider-specific non-secret configuration. Do not assume one fixed shape. |
| `runs[]` | array, newest first, max 20 | Recent ingestion runs. |
| `runs[].id` | UUID string | Run correlation ID. |
| `runs[].source_id` | UUID string | Parent source ID. |
| `runs[].status` | string | Persisted run state. Polling-active values are `queued`, `running`, `retrying`; also handle `processing`, `partial`, `completed`, and `failed`. |
| `runs[].page_count` | integer | Pages processed so far/finally. |
| `runs[].document_count` | integer | Documents processed so far/finally. |
| `runs[].error` | string or `null` | Safe run failure summary. |
| `category_summaries[]` | array of 25 | One summary per canonical category. |
| `category_summaries[].key` | category enum below | Stable API key. |
| `.label` | string | Frontend-ready English label. |
| `.category_group` | enum `business`, `sales`, `customers`, `operations`, `competitive_intelligence` | Visual grouping. |
| `.mandatory_group` | mandatory-group enum or `null` | Readiness group this category can satisfy. |
| `.status` | normally `missing`, `partial`, or `found` | Extraction coverage state. |
| `.count` | integer ≥ 0 | Extracted item count. |
| `.summary` | string or `null` | 1–2 sentence aggregate description when available. |
| `.confidence` | number or `null` | Extraction/summary confidence, intended range 0–1. |
| `.needs_review` | boolean | Backend review recommendation. |
| `.display.mode` | enum `enumerable`, `aggregate` | Required rendering mode; see below. |
| `.display.items_endpoint` | string | Present only for enumerable mode; fetch paginated records here. |
| `.display.review_progress.reviewed` | integer | Count with review status `approved`, `edited`, or `rejected`, capped at total. |
| `.display.review_progress.total` | integer | Total enumerable items. |
| `.display.breakdown` | array of `{label:string,count:integer}` | Present in aggregate mode; inferred natural subcategories. May be empty. |
| `.display.sample_items` | string array | Present in aggregate mode; representative labels, not full records. May be empty. |
| `missing_data.profile` | array of `company_name`, `timezone`, `industry` | Required profile fields still missing. |
| `missing_data.optional` | category-key array | Missing categories that are not in a mandatory readiness group. |
| `important_missing_data[]` | array | Mandatory groups with no populated category, including confirmed groups. |
| `.requirement` | mandatory-group enum | Missing group. |
| `.acceptable_categories` | category-key array | Any one populated category satisfies the group. |
| `confirmations_needed` | mandatory-group array | Important missing groups not yet explicitly resolved. |
| `confirmations[]` | array | Stored resolutions for this tenant. |
| `.requirement` | mandatory-group enum | Resolved group. |
| `.resolution` | enum `provided`, `not_applicable`, `confidential`, `continue_without` | User decision. |
| `.note` | string or `null` | Optional explanation. |
| `.confirmed_at` | ISO-8601 string | Decision timestamp. |
| `can_continue` | boolean | True only when the profile is complete and every missing mandatory group has a confirmation. |
| `ready_for_autonomous_actions` | boolean | Stricter: true only when `can_continue`, no mandatory group is actually missing, and no `continue_without` resolution exists. |

Canonical category keys, in response order:

```text
products, services, pricing_packages, plans_subscriptions, policies_terms, faqs,
sales_process, lead_qualification, sales_messaging, value_propositions,
common_objections, customer_pain_points, buyer_personas, customer_segments,
target_industries, use_cases, contact_company_information,
communication_preferences, support_process, payment_billing_process,
existing_deals_opportunities, follow_up_patterns, competitors,
differentiators, positioning_angles
```

Mandatory groups and their “any one” members:

- `business_fundamentals`: `products`, `services`, `pricing_packages`, `plans_subscriptions`
- `customer_definition`: `customer_segments`, `buyer_personas`, `target_industries`, `use_cases`
- `value_positioning`: `value_propositions`, `differentiators`, `positioning_angles`
- `process`: `sales_process`, `support_process`, `payment_billing_process`
- `governance`: `policies_terms`

### Adaptive `display.mode`

- Default threshold is 25. Counts `0..25` resolve to `enumerable`; counts `26+` resolve to `aggregate` when summaries are materialized.
- `policies_terms` and `pricing_packages` force `enumerable` regardless of count. Reserved future industry keys `listings` and `contracts` also have forced overrides but are not in the current 25-key response.
- The state endpoint returns the persisted display mode; the frontend must use the returned mode and must not recompute it.
- Aggregate mode intentionally never contains the full list. Render summary, breakdown, and samples.
- Enumerable mode intentionally never embeds records. Fetch `items_endpoint` and render review progress.

### Errors and polling

`401` shared auth errors; `500` database/control-plane failure. This endpoint does not return `404` for an empty tenant state.

Poll only while `progress.runs_active > 0`. Use backoff and avoid simultaneous polling from multiple components. Do not wait for every optional category; use `can_continue` and `confirmations_needed`.

---

## 7. Category items and enumerable review

### 7.1 List category items

`GET /api/v1/onboarding/categories/{key}/items?page=1&page_size=25` — bearer auth required.

Call only when the state entry says `display.mode === "enumerable"`; use its `items_endpoint`. Refetch after an item update or optimistically update the row and progress.

#### Request parameters

| Parameter | Required | Type/validation | Example |
|---|---:|---|---|
| `key` path | yes | canonical category key or supported legacy alias | `pricing_packages` |
| `page` query | no | integer ≥ 1, default 1 | `1` |
| `page_size` query | no | integer 1–100, default 25 | `25` |

No body.

#### Success response

```json
{
  "data": {
    "category": "pricing_packages",
    "items": [
      {
        "id": "b50c5cb7-31de-46b4-a3c6-1fe9c1130dfb",
        "fact_type": "pricing_package",
        "payload": {"name":"Growth","monthly_price":99,"currency":"USD"},
        "citation": {"source_id":"862637ad-b0fc-49ab-b0cf-c66eaf93a33e","page":2},
        "confidence": 0.93,
        "review_status": "pending",
        "approval_status": "draft",
        "reviewer": null,
        "review_reason": null,
        "created_at": "2026-08-10T10:40:12.130111",
        "reviewed_at": null
      }
    ],
    "pagination": {"page":1,"page_size":25,"total":3,"pages":1}
  },
  "meta": {"request_id":"<uuid>","generated_at":"<ISO-8601>"},
  "errors": []
}
```

`payload` and `citation` are arbitrary JSON objects whose keys depend on fact type/source. Do not hardcode one product/policy schema; render known fields and retain unknown fields. `confidence` is a number or `null`. `review_status` values are `pending`, `edited`, `approved`, `rejected`. `approval_status` normally progresses from `draft` to `approved` or `rejected` (historical data may be `superseded`). `reviewer`, `review_reason`, and `reviewed_at` are nullable. `pages` is `0` when `total` is `0`.

Errors: shared `401`; `404 {"detail":"Unknown onboarding category"}`; `422` validation array for bad pagination; `500` database failure.

### 7.2 Edit an item

The canonical provenance-preserving review route is:

`PATCH /knowledge/review/facts/{draft_id}` — bearer auth required.

Request body:

| Field | Required | Type/validation | Example |
|---|---:|---|---|
| `tenant_id` | yes | UUID; must match JWT tenant | `62164916-2780-4478-968f-e74c3bd34a58` |
| `payload` | yes | object; validated against the existing fact type | `{"name":"Growth","monthly_price":109,"currency":"USD"}` |
| `reviewer` | no | string, default `human` | `maya@northstar.example` |
| `reason` | yes | string, 1–1000 chars | `Corrected current website price` |

Success is the full fact object shown under approval below, with `approval_status: "draft"` and `review_status: "edited"`.

Errors: `401`; `403` tenant mismatch/invalid tenant; `404 {"detail":"Fact draft not found for tenant"}`; `409` if no longer draft; `422` body/path or fact-payload validation; `500` persistence failure.

### 7.3 Approve or reject an item

- `POST /knowledge/review/facts/{draft_id}/approve`
- `POST /knowledge/review/facts/{draft_id}/reject`

Both require bearer auth and the same body:

| Field | Required | Type | Example |
|---|---:|---|---|
| `tenant_id` | yes | string containing tenant UUID; must match JWT | `62164916-2780-4478-968f-e74c3bd34a58` |
| `reviewer` | no | string, default `human` | `maya@northstar.example` |
| `reason` | no | string or `null` | `Verified against source` |

```json
{
  "tenant_id": "62164916-2780-4478-968f-e74c3bd34a58",
  "reviewer": "maya@northstar.example",
  "reason": "Verified against source"
}
```

`200 OK`:

```json
{
  "id": "b50c5cb7-31de-46b4-a3c6-1fe9c1130dfb",
  "tenant_id": "62164916-2780-4478-968f-e74c3bd34a58",
  "document_id": "fd9c689a-413d-474a-b2a6-68f168c0ae69",
  "chunk_id": "8a948203-827c-426d-938f-df35bf5fb15e",
  "fact_type": "pricing_package",
  "payload": {"name":"Growth","monthly_price":109,"currency":"USD"},
  "citation": {"page":2,"heading_path":["Pricing","Growth"]},
  "extraction_confidence": 0.93,
  "approval_status": "approved",
  "review_status": "approved",
  "reviewer": "maya@northstar.example",
  "review_reason": "Verified against source",
  "published_record_type": "pricing_package",
  "published_record_id": "e29cc37c-e49d-4614-b7ba-245f2f985bc0",
  "created_at": "2026-08-10T10:40:12.130111",
  "reviewed_at": "2026-08-10T10:45:54.882193"
}
```

Reject returns the same fields with `approval_status` and `review_status` equal to `rejected`; published fields normally remain `null`. `chunk_id`, confidence, reviewer/reason, published fields, and reviewed timestamp may be `null` as applicable.

Errors: `401`; `403` tenant mismatch; `404` own draft not found; `409 {"detail":"Fact draft is already <status>"}`; `422` malformed UUID/body, plus approval can return fact-publication validation errors; `500` persistence/sync failure.

After edit/approve/reject, refetch the item page and state. Approval/rejection is not idempotent: a repeated action returns `409`.

---

## 8. Mandatory-group confirmations

### Method, path, auth, and sequence

`POST /api/v1/onboarding/confirmations` — bearer auth required.

Call after state returns a value in `confirmations_needed`. The response is the updated full state; use it directly. Then proceed when `can_continue` is true or continue adding sources.

### Request body

| Field | Required | Type/validation | Example | Meaning |
|---|---:|---|---|---|
| `requirement` | yes | enum `business_fundamentals`, `customer_definition`, `value_positioning`, `process`, `governance` | `governance` | Missing mandatory group being resolved. |
| `resolution` | yes | enum `provided`, `not_applicable`, `confidential`, `continue_without` | `confidential` | User's explicit decision. |
| `note` | no | string or `null`, max 1000 chars | `Policies are private and will be added later.` | Optional context. |

Unknown extra fields are currently ignored; do not send them.

```json
{
  "requirement": "governance",
  "resolution": "confidential",
  "note": "Policies are private and will be added later."
}
```

### Success response

`200 OK` returns the complete onboarding-state envelope documented in section 6. The stored entry appears in `data.confirmations`, disappears from `confirmations_needed`, and can make `can_continue` true. It does not make missing data exist; therefore `ready_for_autonomous_actions` can remain false.

### Errors

| Status | Body/cause |
|---|---|
| `401` | Missing/invalid bearer token or invalid user claim. |
| `422` | `{"detail":"Unknown mandatory requirement"}` for a non-enum group. |
| `422` | Validation array for missing fields, invalid resolution, or note over 1000 chars. |
| `500` | Confirmation persistence/state rebuild failure. |

Submitting the same requirement updates its existing resolution rather than creating a second entry.

---

## 9. Lead CSV import

The frontend should use the durable job workflow: upload → poll → preview/review → commit. A lighter CSV-only dry preview is also available before creating a job.

### Contactability policy returned to the UI

Policy is resolved per tenant at import time:

- Email is always active.
- `phone` is accepted if an enabled, active tenant channel is `phone`, `voice`, or `sms`.
- `whatsapp` is accepted only if an enabled, active tenant channel is `whatsapp`.
- A valid standard `phone` value can satisfy the WhatsApp method when WhatsApp is active.
- Each row needs at least the tenant's `lead_contact_requirement` distinct accepted methods.
- Rows failing that rule are rejected individually. The batch can commit only if at least 50 accepted rows remain.

The policy object has these exact fields:

```json
{
  "minimum_accepted_rows": 50,
  "minimum_contact_methods": 2,
  "lead_contact_requirement": 2,
  "contactability_rule": "minimum_active_channel_matches",
  "accepted_contact_methods": ["email", "phone", "whatsapp"],
  "active_channel_types": ["email", "voice", "whatsapp"],
  "required_contact_methods": [],
  "row_rejection_mode": "individual",
  "batch_policy": "partial_accept",
  "policy_scope": "tenant",
  "configuration_valid": true,
  "accepted_rows": 61,
  "rejected_rows": 4,
  "can_proceed": true
}
```

The last three count/proceed fields are added in preview/job policy state; base policy responses can omit them. `minimum_contact_methods` and `lead_contact_requirement` are equal compatibility names. `required_contact_methods` is intentionally empty because the requirement is “N of accepted,” not a fixed method. If `configuration_valid` is false, the tenant requires more methods than its active channels make possible; block commit UI and direct the user to channel settings.

### 9.1 Dry-run CSV preview

`POST /api/leads/import/preview` — bearer auth required.

Request is `multipart/form-data` with one required field:

| Field | Type/validation | Example |
|---|---|---|
| `file` | binary CSV upload; non-empty filename; UTF-8/UTF-8-BOM or Latin-1 | `leads.csv` |

No `tenant_id` is accepted; tenant comes from JWT.

`200 OK`:

```json
{
  "rows": [
    {
      "row_index": 0,
      "data": {"email":"lead@example.com","company":"Acme"},
      "errors": []
    },
    {
      "row_index": 1,
      "data": {"email":"not-an-email"},
      "errors": [
        "Tenant requires at least 1 valid active-channel contact method(s); provide: email",
        "Invalid email: not-an-email"
      ]
    }
  ],
  "total": 65,
  "valid_rows": 61,
  "invalid_rows": 4,
  "batch_errors": [],
  "policy": {
    "minimum_accepted_rows": 50,
    "minimum_contact_methods": 1,
    "lead_contact_requirement": 1,
    "contactability_rule": "minimum_active_channel_matches",
    "accepted_contact_methods": ["email"],
    "active_channel_types": ["email"],
    "required_contact_methods": [],
    "row_rejection_mode": "individual",
    "batch_policy": "partial_accept",
    "policy_scope": "tenant",
    "configuration_valid": true,
    "can_proceed": true
  }
}
```

`row_index` is zero-based. `data` is normalized from common CSV header aliases. `errors` contains all row validation messages. If fewer than 50 are valid, `batch_errors` contains:

```json
[{"code":"minimum_accepted_rows_not_met","minimum_accepted_rows":50,"accepted_rows":42,"rejected_rows":8}]
```

Errors: `401`; `400 {"detail":"No file provided"}`; `400 {"detail":"No data rows found in CSV"}`; `422` missing multipart field; `500` tenant-policy/database failure.

### 9.2 Upload/create an import job

`POST /api/leads/import/upload` — bearer auth required and is the canonical job-based import path. `/api/leads/import/async` remains a deprecated compatibility alias; new frontend code must not use it.

Request `multipart/form-data`:

| Field | Required | Type/validation | Example |
|---|---:|---|---|
| `tenant_id` | yes | UUID string; must exactly match JWT tenant | `62164916-2780-4478-968f-e74c3bd34a58` |
| `file` | yes | binary; supported extensions `csv`, `xlsx`, `xls`, `pdf`, `docx`, `txt`, `png`, `jpg`, `jpeg` | `leads.csv` |

`201 Created`:

```json
{
  "job_id": "693dcd77-d87f-4205-b6d6-49d109059871",
  "public_id": "IMP-20260810-AB12CD",
  "filename": "leads.csv",
  "file_type": "csv",
  "status": "pending",
  "message": "File uploaded successfully. Processing in background."
}
```

`job_id` is used for every subsequent call. `public_id` is display-friendly and can be empty in legacy rows. `file_type` is detected extension/type. `status` is the initial job status.

Errors:

| Status | Body/cause |
|---|---|
| `400` | `{"detail":"No file provided"}` or unsupported file-type detail. |
| `401` | Shared auth error. |
| `403` | `{"detail":"Invalid tenant identifier"}` or `{"detail":"Tenant does not match authenticated user"}`. |
| `422` | Missing multipart fields. For a CSV with fewer than 50 candidate rows: `{"detail":{"code":"minimum_accepted_rows_not_met","minimum_accepted_rows":50,"accepted_rows":0,"candidate_rows":12,"partial_accept":true}}`. |
| `500` | Upload/object parsing/job persistence failure. |

### 9.3 Poll job status

`GET /api/leads/import/{job_id}` — bearer auth required; no body.

```json
{
  "id": "693dcd77-d87f-4205-b6d6-49d109059871",
  "public_id": "IMP-20260810-AB12CD",
  "tenant_id": "62164916-2780-4478-968f-e74c3bd34a58",
  "filename": "leads.csv",
  "file_type": "csv",
  "status": "preview_ready",
  "uploaded_by": null,
  "total_rows": 65,
  "valid_rows": 61,
  "duplicate_rows": 3,
  "invalid_rows": 4,
  "statistics": {"import_policy":{"accepted_rows":61,"rejected_rows":4,"can_proceed":true}},
  "error_message": null,
  "created_at": "2026-08-10T11:00:00.000000",
  "completed_at": null
}
```

All fields are present; nullable fields are shown. `statistics` is an extensible object—read `statistics.import_policy` if present but tolerate additional keys. Status values currently used are `pending`, `processing`, `parsing`, `extracting`, `enriching`, `intelligence`, `correcting`, `validating`, `reviewing`, `preview_ready`, `committed`, `failed`.

Poll with backoff until `preview_ready`, `failed`, or `committed`. On `failed`, show `error_message`. Errors: `401`; `404 {"detail":"Import job not found"}` for invalid, absent, or other-tenant job; `500` DB failure.

### 9.4 Fetch the durable preview

`GET /api/leads/import/{job_id}/preview` — bearer auth required; no body.

`200 OK` full shape:

```json
{
  "job_id": "693dcd77-d87f-4205-b6d6-49d109059871",
  "public_id": "IMP-20260810-AB12CD",
  "filename": "leads.csv",
  "file_type": "csv",
  "status": "preview_ready",
  "detected_columns": ["document_classification", "quality", "import_policy", "metrics"],
  "statistics": {},
  "total_rows": 65,
  "document_classification": null,
  "import_policy": {
    "minimum_accepted_rows": 50,
    "minimum_contact_methods": 1,
    "lead_contact_requirement": 1,
    "contactability_rule": "minimum_active_channel_matches",
    "accepted_contact_methods": ["email"],
    "active_channel_types": ["email"],
    "required_contact_methods": [],
    "row_rejection_mode": "individual",
    "batch_policy": "partial_accept",
    "policy_scope": "tenant",
    "configuration_valid": true,
    "accepted_rows": 61,
    "rejected_rows": 4,
    "can_proceed": true
  },
  "new_rows": [],
  "update_rows": [],
  "duplicate_rows": [],
  "conflict_rows": [],
  "invalid_rows": [],
  "spam_rows": [],
  "needs_review_rows": [],
  "ignored_rows": []
}
```

Each row in any row array has this complete shape:

```json
{
  "id": "50b12c4b-c04a-43a8-91cc-e16ed2237660",
  "row_index": 0,
  "raw_data": {"Email":"lead@example.com"},
  "normalized_data": {"email":"lead@example.com"},
  "extracted_data": {"email":"lead@example.com","company":"Acme"},
  "confidence": 0.92,
  "confidence_reason": "Structured CSV mapping",
  "duplicate_probability": 0,
  "source_page": null,
  "source_row": 2,
  "quality_score": 82,
  "quality_grade": "A",
  "quality_reasons": ["Valid active-channel email"],
  "quality_flags": [],
  "intelligence": {},
  "duplicate": false,
  "duplicate_of": null,
  "match_reason": null,
  "status": "new",
  "selected": true,
  "error": null
}
```

At present, despite its name, `detected_columns` is populated from the top-level keys of `statistics`; treat it as informational rather than as a reliable CSV header list. `id` is row UUID; `row_index` is zero-based; the three data objects preserve successive representations. Every field from `normalized_data` through `error` can be `null` where shown by its type. Row `status` values are `pending`, `new`, `update`, `duplicate`, `conflict`, `invalid`, `spam`, `needs_review`, `committed`, `skipped`. Only selected eligible `new`/`update` records are normally committed.

Errors: `401`; `404` missing/other-tenant job; `409 {"detail":"Job <id> is in status '<current>', expected 'preview_ready'"}`; `422` policy detail object when accepted rows are below 50; `500` DB failure.

### 9.5 Optional row review controls

- `PUT /api/leads/import/{job_id}/rows/{row_id}` with JSON `{"updates":{...fields...}}` merges fields into `extracted_data`, adds `user_edited: true`, and returns the full row shape.
- `POST /api/leads/import/{job_id}/rows/{row_id}/ignore` has no body and returns the full row shape with skipped/unselected state.
- `POST /api/leads/import/{job_id}/bulk` with `{"action":"ignore|reset|spam|select|deselect","row_ids":["<uuid>"]}` returns `{"action":"ignore","affected_rows":1}`.

All require bearer auth. They return `404` for job/row absence, `422` for malformed bodies/UUIDs, and `500` for persistence failure. Use only the five listed bulk action strings; the current schema types `action` as a free string even though the service only implements those values.

### 9.6 Commit

`POST /api/leads/import/{job_id}/commit` — bearer auth required; no body.

Call only from a `preview_ready` job when `import_policy.can_proceed` is true.

`200 OK`:

```json
{
  "job_id": "693dcd77-d87f-4205-b6d6-49d109059871",
  "public_id": "IMP-20260810-AB12CD",
  "status": "committed",
  "total_imported": 58,
  "total_new": 55,
  "total_updated": 3,
  "total_duplicates": 3,
  "total_conflicts": 0,
  "total_invalid": 0,
  "accepted_rows": 61,
  "rejected_rows": 4,
  "policy": {
    "minimum_accepted_rows": 50,
    "lead_contact_requirement": 1,
    "accepted_contact_methods": ["email"],
    "row_rejection_mode": "individual",
    "batch_policy": "partial_accept",
    "can_proceed": true
  },
  "message": "Imported 58 leads (55 new, 3 updates); 3 duplicates, 0 conflicts, 0 invalid",
  "flow_enrollment": {"status":"enrolled","enrolled":55}
}
```

All count fields are integers. `policy` is the resolved policy object (it can contain all fields shown earlier). `flow_enrollment` is a provider/workflow-specific object or `null`; treat it as extensible. `total_imported` need not equal `accepted_rows` because duplicates, conflicts, selection, and updates affect persistence. `message` is generated from the counts and must not be matched as a fixed literal. In the current implementation `total_invalid` counts invalid attempts made during commit, while policy-rejected rows are represented by `rejected_rows`; use `rejected_rows` for the validation-rejection UI.

Errors:

| Status | Body/cause |
|---|---|
| `401` | Shared auth error. |
| `404` | Missing/invalid/other-tenant job. |
| `409` | Job is not exactly `preview_ready`. |
| `422` | `{"detail":{"code":"minimum_accepted_rows_not_met","accepted_rows":42,"minimum_accepted_rows":50,"partial_accept":true}}`. |
| `500` | Lead persistence, memory projection, event publication, or flow-enrollment failure. |

Commit is not a retry-safe idempotent request at the HTTP contract level; after a network ambiguity, poll the job first. A committed job returns `409` on a second commit.

---

## 10. Knowledge query — streamed SSE answer

### Method, path, auth, and sequence

`POST /api/v1/knowledge/query` — bearer auth required.

Use after knowledge ingestion has completed and approved chunks exist. It embeds the query, searches only approved Qdrant chunks for the JWT tenant (plus optional exact category), emits sources, then streams Mistral-generated answer text.

### Request body

Unknown fields are rejected.

| Field | Required | Type/validation | Example | Meaning |
|---|---:|---|---|---|
| `query` | yes | string, 1–4000 chars | `What are our Growth plan limits?` | User question. Whitespace-only currently passes schema validation. |
| `category` | no | string or `null`, max 100 chars | `pricing_packages` | Exact Qdrant category filter; it is not normalized by this endpoint. Prefer canonical keys. |
| `top_k` | no | integer 1–20 or `null`; default server config is 8 | `8` | Maximum evidence chunks. |

```json
{
  "query": "What are our Growth plan limits?",
  "category": "pricing_packages",
  "top_k": 8
}
```

### SSE response contract

Success starts as `200 OK` with:

```http
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache
X-Accel-Buffering: no
```

Events are UTF-8 SSE frames: `event: <type>`, one compact JSON `data:` line, blank line. The order is:

1. Exactly one `sources` event after retrieval and before answer generation.
2. Zero or more `token` events.
3. Exactly one `done` event on success, **or** an `error` event if generation fails after streaming starts.

```text
event: sources
data: {"sources":[{"chunk_id":"chunk-123","score":0.917,"category":"pricing_packages","heading_path":["Pricing","Growth"],"chunk_type":"table","source_id":"862637ad-b0fc-49ab-b0cf-c66eaf93a33e"}]}

event: token
data: {"text":"The Growth plan "}

event: token
data: {"text":"supports up to 25 users."}

event: done
data: {"status":"complete"}

```

Source fields:

| Field | Type | Meaning |
|---|---|---|
| `chunk_id` | string | Retrieved chunk identifier. |
| `score` | number | Qdrant similarity score. |
| `category` | string or `null` | Stored category. |
| `heading_path` | string array | Source hierarchy used in prompt/context. |
| `chunk_type` | string | Structure type such as `prose`, `table`, `faq`, or slide-related type. |
| `source_id` | string | Knowledge source UUID/string. |

The raw chunk text and tenant ID are deliberately not exposed in `sources`. Concatenate `token.data.text` in arrival order. `done.data.status` is currently `complete`.

Generation-time error event:

```text
event: error
data: {"code":"provider_rate_limited","message":"The AI provider is temporarily rate limited. Please retry shortly.","retryable":true}

```

Possible public AI codes are:

| Code | HTTP status if failure occurs before stream | Message | Retryable |
|---|---:|---|---:|
| `provider_rate_limited` | `429` | `The AI provider is temporarily rate limited. Please retry shortly.` | true |
| `provider_timeout` | `504` | `The AI provider timed out. Please retry.` | true |
| `provider_unavailable` | `503` | `The AI provider is temporarily unavailable. Please retry.` | true |
| `provider_not_configured` | `503` | `AI generation is not configured for this environment.` | false |

If embedding/retrieval preparation fails before headers, the body is JSON:

```json
{
  "detail": {
    "code": "provider_timeout",
    "message": "The AI provider timed out. Please retry.",
    "retryable": true
  }
}
```

If generation fails after the response has started, HTTP status remains `200`; detect the SSE `error` event and the absence of `done`. Other errors are shared `401`, `422` request validation, and opaque `500` for unexpected Qdrant/internal failures.

### Browser client example

Native `EventSource` cannot issue this authenticated `POST` with a bearer header. Use `fetch` and an SSE parser (the example below uses `eventsource-parser`). Do not automatically reconnect a completed/error stream; this endpoint does not support `Last-Event-ID` or resumable generation.

```ts
import { createParser, type EventSourceMessage } from 'eventsource-parser';

type KnowledgeSource = {
  chunk_id: string;
  score: number;
  category: string | null;
  heading_path: string[];
  chunk_type: string;
  source_id: string;
};

export async function queryKnowledge(
  apiOrigin: string,
  accessToken: string,
  body: { query: string; category?: string | null; top_k?: number | null },
  handlers: {
    onSources(sources: KnowledgeSource[]): void;
    onToken(text: string): void;
    onDone(): void;
    onError(error: { code: string; message: string; retryable: boolean }): void;
  },
  signal?: AbortSignal,
) {
  const response = await fetch(`${apiOrigin}/api/v1/knowledge/query`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw Object.assign(new Error('Knowledge query failed'), { status: response.status, body: error });
  }
  if (!response.body) throw new Error('Streaming response body is unavailable');

  const parser = createParser({
    onEvent(event: EventSourceMessage) {
      const value = JSON.parse(event.data);
      if (event.event === 'sources') handlers.onSources(value.sources);
      else if (event.event === 'token') handlers.onToken(value.text);
      else if (event.event === 'done') handlers.onDone();
      else if (event.event === 'error') handlers.onError(value);
    },
  });

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    parser.feed(value);
  }
}
```

Use `AbortController` when the user cancels or leaves the page. If a proxy buffers despite `X-Accel-Buffering: no`, disable proxy buffering for this path. A transport disconnect is ambiguous and cannot resume; offer a manual retry.

---

## 11. End-to-end frontend call order

1. Register/sign in with email/password, or run the combined Google auth full-page redirect flow and immediately exchange its query-string code.
2. Store session tokens and tenant ID; complete the existing company/workspace profile step.
3. Connect Google Workspace through the popup and/or add a website source.
4. Poll `GET /api/v1/onboarding/state` while runs are active.
5. Render every category from `category_summaries`:
   - aggregate → summary/breakdown/samples;
   - enumerable → fetch `display.items_endpoint`, then edit/approve/reject.
6. For each `confirmations_needed` entry, add data or submit a confirmation.
7. Import leads: optional dry preview, upload, poll, durable preview/review, commit.
8. Continue when `can_continue` is true. Enable autonomous actions only when `ready_for_autonomous_actions` is true.
9. Use the knowledge query stream after approved knowledge has been indexed.

## 12. Frontend implementation warnings checklist

- **Google auth scope:** Google registration/sign-in deliberately includes Workspace consent and automatically queues all four resource syncs; it is not an identity-only flow.
- **Popup blocking:** open a blank window synchronously, then navigate after the authenticated start request.
- **Public Google auth callback:** read and immediately remove its one-time `exchange_code` from `/auth/callback`; it does not use `postMessage`.
- **Workspace OAuth cancellation:** the separate popup callback can still receive a request without `code`, producing a 422 page and no `postMessage`; detect popup closure and timeout.
- **Workspace `postMessage` validation:** verify API origin, popup window source, provider, and message type.
- **Token timing:** both access and current refresh tokens are short-lived; refresh early and serialize refresh attempts.
- **Tenant isolation:** never take tenant choice from form state. Legacy fields must equal the JWT tenant.
- **Adaptive summaries:** render the returned `display.mode`; never fetch/render thousands of aggregate items from state.
- **Polling:** back off, pause hidden tabs, and stop on terminal states.
- **Lead partial acceptance:** invalid rows do not abort a batch, but fewer than 50 accepted rows blocks commit.
- **SSE auth:** use streaming `fetch`, not native `EventSource`; handle both pre-stream JSON errors and in-stream `error` events.
- **SSE reconnect:** streams are not resumable and have no event IDs. Do not silently auto-reconnect and duplicate an answer.
