# How-To Guide: Run, Integrate, and Test CRM Gateway

This guide describes how to run the CRM Gateway, seed a test customer connection, and verify the OAuth authentication flow and standard endpoints.

---

## 1. Setup & Environment Initialisation

Ensure you are using the virtual environment and have installed the dependencies:

```bash
# 1. Activate the virtual environment (if not already done)
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1
# On Windows Command Prompt:
venv\Scripts\activate.bat
# On macOS/Linux:
source venv/bin/activate

# 2. Install requirements
pip install -r requirements.txt
```

---

## 2. Configuration Settings (`.env`)

Create or update the `.env` file at the root of the workspace to set up credentials and the database connection:

```ini
# Environment settings
ENV=development
DEBUG=true

# Database Path
DATABASE_URL=sqlite+aiosqlite:///./crm_gateway.db

# Symmetric Encryption Key (32-byte url-safe base64 key)
# Run `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
# to generate a stable key, or leave it blank to auto-generate a temporary one on startup.
ENCRYPTION_KEY=

# HubSpot App OAuth Client Configuration
HUBSPOT_CLIENT_ID=your-hubspot-client-id
HUBSPOT_CLIENT_SECRET=your-hubspot-client-secret
HUBSPOT_REDIRECT_URI=http://localhost:8000/oauth/hubspot/callback
```

---

## 3. Seeding a Test Customer Connection

To test CRM endpoints without completing the live OAuth redirect loop, you can seed a connection for **`test_customer_1`** in the database using the seeding script:

```bash
python seed_test_user.py
```

1. Run the script in your terminal.
2. It will prompt you for:
   - **Access Token**: Provide your real HubSpot Private App Token/Access Token, or press Enter for a mock `dummy-hubspot-token`.
   - **Refresh Token**: Provide your refresh token, or press Enter for `dummy-refresh-token`.
   - **Hub ID & Portal Name**: Set custom portal details or use defaults.
3. The script encrypts the tokens and saves the connection record to `crm_gateway.db`.

---

## 4. Running the Gateway Server

Start the FastAPI application with:

```bash
uvicorn app:app --reload
```

The server launches at `http://127.0.0.1:8000`.

- **Swagger Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc Documentation**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 5. Testing & Executing API Requests

### Option A: Retrieve CRM Data for a Customer (Your Goal)

After seeding `test_customer_1` (or logging in through OAuth), fetch contacts from the CRM gateway by passing the provider and user identifier headers:

```bash
curl -X GET "http://127.0.0.1:8000/contacts" \
  -H "X-CRM-Provider: hubspot" \
  -H "X-User-ID: test_customer_1"
```

_Note: Under the hood, `GenericClient` checks the database, decrypts the token, automatically executes a token refresh flow with HubSpot if the token is expired, and returns the valid data!_

---

### Option B: Testing live OAuth Flows

1. **Initiate Login**:
   Open a browser and navigate to:

   ```text
   http://localhost:8000/oauth/hubspot/login?user_id=test_customer_1
   ```

   _This saves a secure random state in the database and redirects the browser to the HubSpot Authorization screen._

2. **Authenticate & Authorize**:
   Log into your HubSpot developer portal, select an account/sandbox, and authorize the scope permissions.

3. **Callback Processing**:
   HubSpot redirects back to:
   ```text
   http://localhost:8000/oauth/hubspot/callback?code=...&state=...
   ```
   _The server validates the CSRF state token, exchanges the auth code for access/refresh tokens, queries details, encrypts, writes the connection to the SQLite database, and displays a polished integration success landing page._

---

### Option C: Auxiliary Integration Utilities

#### 1. Check Connection Status

To view active integrations and scope permissions without exposing secrets, request:

```bash
curl -X GET "http://127.0.0.1:8000/oauth/hubspot/status?user_id=test_customer_1"
```

#### 2. Manual Token Refresh

Force the Token Manager to refresh the access token manually:

```bash
curl -X POST "http://127.0.0.1:8000/oauth/hubspot/refresh?user_id=test_customer_1"
```

#### 3. Disconnect Integrations

Revoke access tokens and clean up the database connection record:

```bash
curl -X DELETE "http://127.0.0.1:8000/oauth/hubspot/disconnect?user_id=test_customer_1"
```
