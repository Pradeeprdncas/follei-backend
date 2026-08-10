# Follei runtime services

The default startup profile is deliberately limited to onboarding knowledge
ingestion, Google Workspace synchronization, website crawling, verification,
and retrieval/generation.

## Default Python processes

| Process | Entrypoint | Responsibility |
|---|---|---|
| API | `uvicorn app.main:app` | OAuth callbacks, onboarding/readiness checks, ingestion APIs, query SSE |
| Indexing worker | `app.workers.indexing_consumer` | Parse, classify, chunk, batch-embed, and write PostgreSQL/Qdrant records |
| Knowledge-sync worker | `app.workers.knowledge_sync_consumer` | Durable PostgreSQL outbox projection into FerretDB/Qdrant |
| Google Workspace worker | `app.workers.google_workspace_worker` | Independent Gmail, Drive, Contacts, and Calendar synchronization |
| Website ingestion worker | `app.workers.website_ingestion_worker` | SSRF-safe crawling, document discovery, and indexing fan-out |

Google OAuth itself runs in the API process. The Google worker performs the
asynchronous resource synchronization after OAuth completes.

## Required infrastructure

| Service | Why it remains required |
|---|---|
| PostgreSQL | Tenant state, OAuth connections, sources, runs, jobs, summaries, confirmations |
| Redis | Indexing deduplication and API cache primitives |
| Kafka + Zookeeper | Durable website, Google, and indexing job queues |
| MinIO | Durable originals and downloaded website/Drive/Gmail attachments |
| FerretDB + its DocumentDB/Postgres service | Chunk text and structural metadata |
| Qdrant | Tenant-filtered embeddings and retrieval |

These stores are dependencies of the five core processes; they are not extra
business workers.

## Optional full profile

`--full` additionally starts conversation analysis, lead scoring, mail
automation, flow execution, and HubSpot synchronization. Local llama.cpp does
not auto-start; set `LOCAL_LLM_AUTO_START=true` only when the legacy local/voice
path is intentionally used.

## Commands

```bash
./start.sh                 # lightweight default
./start.sh --check         # imports/config/service plan only
./start.sh --no-infra      # external stores and Kafka
./start.sh --install-browser
./start.sh --full
```

Windows equivalents:

```bat
start.bat --check --no-pause
start.bat --no-open --no-pause
start.bat --install-browser
start.bat --full
```

Install the light environment with `requirements-core.txt`. Install
`requirements-optional-ai.txt` only for the local-model/voice profile.

On Debian/Ubuntu, install the OS virtual-environment support once if Python
reports that `ensurepip` is unavailable:

```bash
sudo apt install python3-venv
```

The launchers create `.venv` and install the selected requirement profile when
needed. They do not install browsers by default and never start the optional
local model automatically.
