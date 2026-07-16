# Follei Backend — Project Status

## Current state

Follei Backend is a FastAPI-based autonomous business workforce platform. The cleaned repository contains application source, database migrations, deployment files, tests, documentation, and configuration templates. Local model data, credentials, vector indexes, logs, uploads, generated outputs, development environments, and one-off verification scripts are excluded from version control.

## System 1 — Business Intelligence

System 1 turns business material into tenant-scoped knowledge. Documents enter through the knowledge upload API, are parsed into pages and layout-aware chunks, classified and enriched with metadata, stored in PostgreSQL, embedded, and indexed in Qdrant. The MCP integration layer provides connector modules for Gmail, Outlook, Drive, CRM, Slack, Teams, WhatsApp, Calendar, and ERP; connected-source sync needs credentials and deployment configuration.

## System 2 — Knowledge System

System 2 supplies grounded context to AI workers using four layers:

1. PostgreSQL structured records for business facts and operational data.
2. Qdrant vectors for semantic retrieval of document chunks.
3. PostgreSQL entity and relation tables for the business knowledge graph.
4. FerretDB-compatible flexible context/memory records for evolving company, customer, and conversation facts.

Retrieval is tenant-aware: the orchestrator requires an authenticated tenant, retrieves relevant structured/vector/memory context, and returns bounded grounded context for an AI worker. The RAG API supports ingest, query, streaming, caching, routing statistics, and conversation history.

## Verification

- `python -m compileall -q app` — passed.
- `python -m pytest app/services/mcp/tests/test_connectors.py -q` — 17 passed.

## Delivery notes

Run `pip install -r requirements.txt`, provide environment variables through a local `.env`, start PostgreSQL/Redis/Qdrant with Docker Compose, apply `alembic upgrade head`, then start `uvicorn app.main:app --reload`.
