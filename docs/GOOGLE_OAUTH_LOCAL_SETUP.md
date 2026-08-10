# Google OAuth local setup

Google compares OAuth redirect URIs as exact strings. `localhost` and
`127.0.0.1` are different, and the public account-auth callback and the
authenticated Workspace-connector callback are different endpoints.

Add these exact Authorized redirect URIs to the OAuth 2.0 Web application in
Google Cloud Console:

```text
http://localhost:8000/api/v1/auth/google/callback
http://localhost:8000/api/v1/integrations/google-workspace/oauth/callback
http://localhost:8000/api/email-connections/gmail/oauth/callback
```

If a developer deliberately runs the frontend/backend using `127.0.0.1`, also
register the equivalent three `http://127.0.0.1:8000/...` values and set the
backend environment to those exact values. Do not mix hosts between Google
Cloud and the backend environment.

Recommended local `.env` values:

```dotenv
GOOGLE_AUTH_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
GOOGLE_WORKSPACE_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/integrations/google-workspace/oauth/callback
GMAIL_OAUTH_REDIRECT_URI=http://localhost:8000/api/email-connections/gmail/oauth/callback
FRONTEND_BASE_URL=http://localhost:3000
```

Restart the backend after changing `.env`. Both startup scripts print the
effective redirect URIs; verify those lines before testing OAuth.

## Which start endpoint to call

Registration and sign-in use this public request, with no bearer token and no
body:

```http
POST /api/v1/auth/google/start
```

Do not use `/api/v1/integrations/google-workspace/oauth/start` on a sign-in or
sign-up page. That route is the separate connector for an already authenticated
tenant and intentionally requires a bearer token so one tenant cannot attach a
Google account to another tenant.
