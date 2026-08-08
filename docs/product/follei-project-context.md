so you know weverything about the project here like this is the whole project that has been done and we're gonna use all these agin and agin because we have these as a main data and we have to have a foder where we store tghis and on the other hand i need a new brnch - old follei where thee are stored and on tmain branch i need a fresh page where i can see all the thin and the thing is that i wanna make a prper onboarding things and maybe we'll reuse the code so comp[are the docs and all so helpme wity these and then start with the onboarding and my plan is that we'll start building with gogle oauth my .env has all google ckient and secret and all so we'll start with thi flow basically we'll frst have  login pageand they'll give continue with gooogle and it shuld fetch almost whatever details that are possible from the google from thi list   Set up your workspace
Import Data
Connect Your Tools
Tell us a bit about your team to customize your
experience.
STEP 3 OF 3
Bring your existing records into SaasFlow. Start by uploading a file or choosing a
predefined import template to map your fields automatically.
Supercharge your workflow by connecting your favorite communication and
CRM tools. Sync data seamlessly across your existing ecosystem.
Sign in
Company Details
QUICK TEMPLATES
Start building better SaaS workflows today.
Create your account
Tell us about your organization to help us tailor your
SaaSFlow experience.
Import Contacts
Start building better SaaS workflows today.
How do you define your Customer?
Standard mapping for leads,
prospects, and individuals.
SUITE
You're Ready.
Workspace Name
BASIC INFO
Email
Work Email
Import Companies
Google Workspace
Microsoft 365
Freshsales
Your workspace has been created successfully. All
systems are initialized and ready for your team.
First Name
Last Name
Company Name
Company Website
Accounts, organizations, and
firmographic data.
Unified productivity suite for teams.
Cloud-based subscription to office apps.
All-in-one sales CRM for better pipeline.
First Name
Last Name
Company Website
Password
Password
INDUSTRY & SECTOR
Connect
Connect
Connect
Go to Dashboard
Import Your First Lead
Work Email
Work Email
YOUR ROLE
Import Deals
Remember Me
Forgot Password?
Select Industry
Opportunities, pipelines, and
revenue projections.
Continue
Password
Founder
Sales Manager
Sales Exec
Password
Drag & Drop Files Here
CHAT
Finish setting up your workspace
COMPANY SIZE
0 / 4 COMPLETED
or
Password strength
or click to browse your computer
Migrate from CRM
Outlook
Complete these steps to get the most out of SaasFlow.
Marketing
Other
1-10
11-50
51-200
201-500
500+
.CSV
.XLSX
WhatsApp Business
Slack
Continue with Google
I agree to the Terms of Service and Privacy Policy.
Personal organizer and email manager.
Connect Email
To do
Reach customers on the world's most
popular chat app.
Where work happens—messaging and
collaboration.
Sync your inbox to track communications automatically.
Continue
LOCATION
TIMEZONE
Select Files
Continue
Country
Time Zone
Connect
Connect
Connect
Import Contacts
To do
New to Follei?
Sign Up
Bring in your existing leads via CSV or CRM integration.
Already have an account? 
Sign in
Invite Team
To do
Setup nearly complete
Complete Setup
CRM
Add collaborators to share data and manage workflows together.
HubSpot
Salesforce
Zoho CRM
Create Pipeline
To do
Customize your deal stages to match your sales process.
Skip for now
Continue Mapping
CRM, marketing, and sales software for
growth.
The world's #1 customer relationship
management platform.
Online CRM software for managing sales,
marketing, and support.
© 2024 SaaSFlow. All rights reserved.
Terms
Privacy
Connect
Connect
Connect
© 2024 SaaSFlow. All rights reserved.
Terms
Privacy
© 2024 SaaSFlow. All rights reserved.
Terms
Privacy
...
see more
Connect your Google Workspace
Google Workspace connected
Connect your business Google account to
securely sync the information Follei needs to
power your sales workspace.
Skip for now
Finish Setup
The following services are now securely synced with Follei.
© 2024 SaaSFlow. All rights reserved.
Terms
Privacy
Gmail
Contacts
Gmail
Access your business email conversations
Calendar
Drive
Google Contacts
Sync contacts and customer information
Connecting your Google Workspace...
Google Calendar
Manage meetings and follow-ups
Google Drive
Authenticating and verifying permissions
Store and access relevant sales files
Continue with Google
We'll ask for permission before connecting your account.
Skip for now
Your data stays secure. Follei only accesses the permissions
required to provide CRM and AI-powered sales features. 
Go to Dashboard
Learn
more an finally after fetchng the data tere there should be anther google api that should be like this ns ## Repo / branch setup

- `git checkout -b old-follei` from current state, push it — that preserves the existing codebase (the tts-with-bant- work, the 143-table schema, all of it) as a reference branch you can pull specific pieces from without it cluttering the fresh build.
- On `main`, start clean, but add a `/docs/product` folder and commit the source docs into it (Follei Product Design PDF, the platform proposal, the SaaSFlow onboarding screenshots/reference) — not as inspiration floating around your notes app, but as versioned repo artifacts the whole team can point to. That's your "main data" folder.

## Single schema file vs. separate files — go separate, split by domain

For a project with ~140+ tables across tenancy, knowledge, leads, workflows, channels, integrations, and billing, one giant schema file becomes a merge-conflict machine the moment more than one engineer touches it, and it makes it hard to reason about which tables belong to which service boundary. Split by domain, one file per bounded context:

```
app/models/
  tenant.py        # Tenant, User, ChannelConnection
  knowledge.py      # KnowledgeSource, Document, Chunk (metadata only — vectors live in Qdrant)
  lead.py           # Lead, LeadVerification
  workflow.py       # WorkflowDefinition, WorkflowNode, WorkflowVersion, ApprovalState
  integration.py    # GoogleWorkspaceConnection, CRMConnection, WebsiteConnector
  campaign.py       # Campaign, CampaignAsset
```

All of them import a single shared `Base` (declarative base) from `app/db/base.py`, so Alembic still sees one unified metadata graph for migrations — you get file-level separation without losing schema-level consistency. Mirror the same split in `schemas/` (Pydantic) and `routers/` — a file in `models/lead.py` has a matching `schemas/lead.py` and `routers/lead.py`. This is the structure that scales past a handful of engineers; a single schema file only stays comfortable for small, single-owner projects.

## Recommended project structure

```
follei-backend/
├── app/
│   ├── core/              # config, security, db session, settings
│   ├── db/
│   │   ├── base.py        # shared declarative Base
│   │   └── session.py
│   ├── models/             # SQLAlchemy, split by domain (above)
│   ├── schemas/             # Pydantic request/response, mirrors models/
│   ├── routers/             # FastAPI routers, mirrors models/, versioned under /api/v1
│   ├── services/             # business logic — one file per domain, called by routers
│   │   ├── onboarding_service.py
│   │   ├── google_workspace_service.py
│   │   ├── ingestion_service.py
│   │   ├── website_connector_service.py
│   │   └── workflow_service.py
│   ├── integrations/          # thin external-API adapters, no business logic
│   │   ├── google/             # oauth.py, gmail.py, drive.py, calendar.py, contacts.py
│   │   ├── website_scraper/
│   │   └── crm/                 # empty/stubbed for now — post-onboarding
│   ├── workers/                 # async consumers — Kafka event handlers / Celery tasks
│   │   ├── tenant_provisioning.py
│   │   ├── knowledge_ingestion.py
│   │   └── website_scrape_scheduler.py
│   └── main.py
├── alembic/
├── tests/
└── docs/product/              # the reference docs, checked in
```

**Why services + integrations are separate**: routers stay thin (validate → call service → return), services hold the actual decision logic, and integrations are pure adapters with no business rules — so when Google changes an API or you swap an ESP, you touch one adapter file, not logic scattered across routers.

## Google Workspace — going deep like the SaaSFlow reference

The screenshots show the right shape: OAuth consent → explicit "connecting Gmail / Contacts / Calendar / Drive" checklist → confirmation. Backend-wise:

- **Scopes**: request Gmail (read + send), Drive (read), Calendar (read), Contacts (read) at once during the initial consent screen — Google supports incremental auth, but front-loading the scopes you know you'll need avoids a second consent round-trip mid-onboarding.
- **Initial pull**: on connect, an async worker does a first full sync — Drive file listing, Gmail message metadata, Contacts, Calendar — writes raw references to Postgres (`google_sync_state` table: resource type, last sync token, status) and queues content into the knowledge ingestion pipeline you already have.
- **Ongoing sync, not just once**: use Drive's `changes.list` API and Gmail's `history.list` (with push notifications via Google Cloud Pub/Sub if you want near-real-time instead of polling) so the knowledge base stays current without re-pulling everything. This is what "read everything from the company continuously" actually requires — a sync-token-based incremental job, not a one-time ingestion.

## Website connector

Same pattern as Google, as its own integration:

- `WebsiteConnector` model: tenant_id, url, crawl frequency, last_crawled_at, content_hash.
- A scheduled worker (Kafka-triggered or a simple cron/Celery beat) crawls the site periodically, diffs content against `content_hash` to avoid reprocessing unchanged pages, and only pushes *changed* pages into the same chunking/ingestion pipeline as documents.
- Respect `robots.txt` and rate-limit per domain — this is a background job, not something onboarding waits on; onboarding just captures the URL and kicks off the first crawl.

This keeps everything — Google, website, and (later) CRM — as interchangeable "knowledge source" integrations feeding one ingestion pipeline, rather than three different pipelines to maintain. this is the plan and basiclly this 