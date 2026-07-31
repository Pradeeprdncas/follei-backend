# Follei tenant Gmail OAuth

## What is implemented

Each tenant can use one Google mailbox as:

- the business inbox Follei monitors;
- the sender for AI auto-replies;
- the sender for scheduled or immediate email campaigns.

The Follei login email and the connected Gmail address may be the same, but
they are separate concepts. The Follei password is never used to access Gmail.
Google returns OAuth tokens after the mailbox owner grants access.

One active Gmail mailbox cannot be shared by multiple Follei tenants. This
prevents two tenants from reading or replying to the same inbox.

## Google Cloud web client

Add this exact development redirect URI to the OAuth 2.0 web client:

```text
http://127.0.0.1:8000/api/email-connections/gmail/oauth/callback
```

Use the exact same host in the browser. `localhost` and `127.0.0.1` are
different redirect origins.

For production, add the public HTTPS API callback. For example, only if the
backend is deployed at `api.coirei.com`:

```text
https://api.coirei.com/api/email-connections/gmail/oauth/callback
```

The OAuth consent screen also needs the Gmail API enabled and the required
test users while the Google app remains in testing mode.

## Environment

Development defaults already point back to the local tenant console:

```dotenv
GMAIL_CLIENT_ID=your-web-client-id
GMAIL_CLIENT_SECRET=your-web-client-secret
GMAIL_OAUTH_REDIRECT_URI=http://127.0.0.1:8000/api/email-connections/gmail/oauth/callback
GMAIL_OAUTH_SUCCESS_URL=http://127.0.0.1:8000/tenant
GMAIL_OAUTH_STATE_TTL_SECONDS=600
```

Production must override both URLs with HTTPS public endpoints.

## User flow

1. Open `http://127.0.0.1:8000/tenant`.
2. Enter the admin and tenant details.
3. Leave Business Gmail blank to reuse the Follei login email, or enter a
   different Google mailbox.
4. Keep Connect Gmail enabled and choose whether to enable auto-reply and
   campaigns.
5. Register. Follei stores a disabled, tenant-owned pending connection and
   redirects the admin to Google.
6. The admin grants access. Google returns to Follei's callback, and Follei
   verifies that the connected address matches the requested address.
7. The encrypted refresh token is stored server-side. The unified mail worker
   then monitors inbound mail, creates or matches leads, ingests attachments,
   stores conversations, and sends replies.

## API flow

Registration:

```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "email": "owner@example.com",
  "password": "a-strong-password1",
  "full_name": "Owner Name",
  "tenant_name": "Example Company",
  "business_email": "owner@example.com",
  "connect_gmail": true,
  "gmail_auto_reply_enabled": true,
  "gmail_campaign_enabled": true
}
```

The authenticated frontend then starts OAuth:

```http
POST /api/email-connections/gmail/oauth/start
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "email_address": "owner@example.com",
  "sender_name": "Example Company",
  "auto_reply_enabled": true,
  "allow_inbound_lead_creation": true,
  "campaign_enabled": true
}
```

Redirect the browser to the returned `authorization_url`.

## Operational notes

- `start.bat` and `startup.sh` start one unified mail worker. Starting a second
  Gmail poller would risk processing the same message twice.
- Gmail is suitable for mailbox-style auto-replies and smaller campaigns.
  Google sending limits still apply. Keep Brevo available for higher-volume
  campaigns, delivery analytics, and dedicated sender domains.
- Google OAuth is the only step that cannot be completed by backend code
  alone: the mailbox owner must sign in and explicitly grant access.
- Publishing this for arbitrary external tenants may require Google OAuth app
  verification because Follei requests Gmail read/modify and send scopes.
