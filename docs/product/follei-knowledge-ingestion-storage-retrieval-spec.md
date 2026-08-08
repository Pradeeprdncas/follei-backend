# Follei — Knowledge Ingestion, Storage & Retrieval Spec

Companion to `follei-onboarding-build-prompt.md`. This covers what that doc left as headlines: database roles, chunking strategy, retrieval, generation, and the concrete record schema for `KnowledgeSource` / `IngestionRun` / jobs / summaries.

---

## 1. Database roles — precise, not just "who owns what"

| Store | Owns | Never stores |
|---|---|---|
| **PostgreSQL** | Tenant/user records, `KnowledgeSource`, `IngestionRun`, per-source jobs, category-summary rows, confirmation/audit records, workflow state, leads, channel connections — anything transactional, auditable, or that the onboarding-state endpoint needs to query fast | Raw document text, chunk content, vectors |
| **FerretDB** | Chunk text + structural metadata (heading path, page number, table/list markers), extracted-fact drafts pending review, tenant memory | Vectors, anything needing joins/transactions across tenants |
| **Qdrant** | Chunk embeddings, with `tenant_id`, `source_id`, `category`, `chunk_id` as filterable payload | Anything that isn't a vector — no summaries, no raw text beyond a short preview field for debugging |
| **MinIO** | Original uploaded files and downloaded documents (PDFs, DOCX, etc. found during crawls) | — |

**The rule that keeps this coherent**: Postgres is the only store the onboarding-state endpoint reads from directly. FerretDB and Qdrant are written to by ingestion workers and read by the RAG query path — never by the UI-facing state endpoint. This is what makes `GET /api/v1/onboarding/state` fast and stable regardless of how much data has landed in Ferret/Qdrant.

### Core Postgres tables

```
knowledge_sources
  id, tenant_id, type (upload | website | google_drive | google_gmail | hubspot | ...),
  status (pending | syncing | classifying | complete | failed),
  config (jsonb — url for website, folder for drive, etc.),
  created_at, updated_at

ingestion_runs
  id, tenant_id, knowledge_source_id, status, started_at, completed_at,
  pages_discovered, pages_processed, documents_discovered, documents_processed,
  error_summary

ingestion_jobs
  id, ingestion_run_id, job_type (crawl_page | download_doc | chunk | embed | classify),
  status, target_url_or_path, attempt_count, last_error, updated_at

category_summaries
  id, tenant_id, category_key, category_group, status (found | missing | partial),
  count, summary_text, confidence, review_status (pending | approved | edited),
  updated_at

confirmations
  id, tenant_id, requirement_key, resolution (provided | not_applicable | confidential | continue_without),
  confirmed_by_user_id, confirmed_at
```

Everything the `/onboarding/state` payload returns (Section 5) is assembled from these five tables — no live queries into FerretDB or Qdrant on that request path.

---

## 2. Chunking strategy — dynamic, not one-size-fits-all

Different content needs different chunking; picking one strategy for everything is what produces bad retrieval later. Route by document structure, detected at ingestion time:

| Content type | Strategy | Why |
|---|---|---|
| Structured docs with headings (product manuals, SOPs, policy docs) | **Layout-aware chunking** — split on heading hierarchy, keep each chunk's full heading path as metadata (`h1 > h2 > h3`) | A chunk without its heading context loses meaning; "10% for orders over $500" means nothing without knowing which policy it's under |
| Tables (pricing sheets, plan comparisons) | **Table-preserving chunking** — never split a table mid-row; keep header row attached to every data-row chunk, or keep small tables whole | Splitting a table destroys the row/column relationship that gives the data meaning |
| Plain prose (website pages, emails, long-form docs) | **Semantic/recursive chunking** — split on paragraph/sentence boundaries with a target size (e.g. 300–500 tokens) and ~15% overlap | Fixed-size chunking mid-sentence hurts embedding quality; overlap prevents losing context at chunk boundaries |
| FAQs | **One chunk per Q&A pair** — never merge multiple FAQs into one chunk | Each Q&A is a complete, independently retrievable unit |
| Slide decks / pitch decks | **One chunk per slide**, with speaker notes appended if present | Slide boundaries are natural semantic boundaries |

**Implementation**: a `chunking_router.py` in `services/knowledge/` inspects the parsed document structure (from the parser — headings detected via HTML/DOCX/PDF layout, tables detected via table-extraction library) and dispatches to the matching strategy function. Every chunk, regardless of strategy, carries the same metadata envelope:

```
chunk_id, source_id, tenant_id, category (assigned after classification),
heading_path, page_number (if applicable), chunk_type (prose | table | faq | slide),
token_count, content (→ FerretDB), embedding (→ Qdrant)
```

Store the chosen strategy per source in `knowledge_sources.config` so re-ingestion is deterministic and debuggable.

---

## 3. Embeddings + generation — Mistral for everything, for now

You have one Mistral API key today — use it for both embeddings and generation, behind the adapter pattern already planned (`services/embedding_service.py`, `services/llm_service.py`), so swapping either one later (a different embedding model, a different LLM) touches one file, not the ingestion or retrieval pipeline.

- **Embeddings**: Mistral's embedding endpoint, batched (don't call per-chunk — batch 20–50 chunks per request). Store the model name/version alongside each vector's payload in Qdrant, so if you ever change embedding models, you know which vectors need re-embedding rather than guessing.
- **Generation**: Mistral's chat/completion endpoint for the RAG answer-generation step. Same adapter — when you later add a second provider (OpenAI/Claude) for quality comparison or fallback, it's a config change, not a rewrite.

### Retrieval ("the generator needs good retrieval to be good")

A strong generator fed weak context still gives weak answers — retrieval quality matters more than model choice here. Build retrieval as:

1. **Query embedding** via the same Mistral embedding model used for ingestion (mismatch between ingestion/query embedding models silently degrades retrieval — keep them locked together in config).
2. **Vector search in Qdrant**, filtered by `tenant_id` (mandatory) and optionally `category` (when the query context makes the category obvious — e.g. a pricing question filters to `category=pricing`).
3. **Optional keyword/hybrid boost**: for exact-match needs (product names, SKUs, policy numbers), a simple keyword filter alongside vector search catches cases pure semantic search misses. Not required for v1, but design the retrieval function signature (`search(query, tenant_id, category=None, hybrid=False)`) so it can be added without a breaking change.
4. **Assemble context** from top-k chunks, each retaining its `heading_path` — pass that path into the prompt so the generator knows *where* the fact came from, not just the fact.
5. **Generate**, streamed back to the client (per the latency plan from the earlier stack doc).

This retrieval function is what both the RAG chat/query endpoints and the category-classification pass (Section 4) call — one retrieval path, not two.

---

## 4. Category taxonomy — expanding from 12 to 25

The audit flagged this as a real gap: schemas, extraction prompts, and summaries all need to grow together, not just a category list. Proposed 25, grouped (confirm against your actual screenshot before locking in — this is a reasonable superset, not a guess to build blind):

**Business fundamentals** (mandatory group — needs ≥1 populated):
`products`, `services`, `pricing`, `plans`

**Customer definition** (mandatory group — needs ≥1 populated):
`customer_segments`, `buyer_personas`, `target_industries`, `use_cases`

**Value & positioning** (mandatory group):
`value_propositions`, `differentiators`, `positioning`

**Process** (mandatory group):
`sales_process`, `support_process`, `payment_process`

**Governance** (mandatory, or explicit `not_applicable` confirmation):
`policies`, `communication_guardrails`, `security_compliance`, `sla`

**Optional — enrich but don't block**:
`faqs`, `competitors`, `objections`, `follow_up_patterns`, `case_studies`, `testimonials`, `brand_voice`, `escalation_rules`, `team_roles`, `integrations_supported`

For each category: an extraction prompt template, a Pydantic schema for the extracted structure, and a summary-generation prompt (turns N extracted records into the 1-2 sentence `summary_text` shown in `category_summaries`). Mandatory groups are satisfied when **at least one** category in that group has `status: found` — matches the "satisfied as groups" rule from the audit.

---

## 5. Onboarding-state endpoint — confirmed contract

Reuse exactly what the audit proposed (`GET /api/v1/onboarding/state`) — it already matches what you described. Two additions worth locking in now:

- `data_summary[].category_group` — so the frontend can render mandatory groups distinctly from optional ones without re-deriving the grouping logic itself.
- `confirmations_needed[]` — a list of `requirement_key` + `satisfy_with[]` + `message`, populated only when a mandatory group is unsatisfied, mirroring `confirmations` table rows still pending. The frontend posts back to `POST /api/v1/onboarding/confirmations` with a `resolution` (`provided` / `not_applicable` / `confidential` / `continue_without`) per requirement — that write is the only mutation this flow needs beyond the sources themselves.

---

## 6. Website ingestion — async, engine-routed

Per the audit: the endpoint must return `202 Accepted` immediately and hand off to a worker. Engine selection logic:

```
def choose_engine(url, site_signals):
    if site_signals.is_js_heavy or needs_clean_markdown:
        return "crawl4ai"
    if site_signals.has_sitemap and expects_large_recurring_crawl:
        return "scrapy"
    return "aiohttp"  # existing crawler, fast path for ordinary sites
```

All three engines sit behind the same safety layer already built (SSRF/private-address rejection, DNS pinning, same-domain restriction, robots.txt, page/byte limits, tenant isolation) — engine choice changes *how* pages are fetched, never bypasses *what's* allowed to be fetched. Progress updates write to `ingestion_jobs` per page/document, which is what powers the `ingestion.pages_processed` counter in the state payload.

**Ownership verification** (per the audit's security note): a "connect website" checkbox is crawl consent, not proof of ownership. Before granting any elevated access (writing back to the site, or treating it as an authoritative source for autonomous actions), require one of: DNS TXT record, `.well-known` file, or HTML meta tag verification.

---

## 7. What this doesn't change

- The 8-step implementation order from the audit stays as the sequencing — this doc fills in steps 2–5 (unified state contract, canonical records, worker-based crawling, chunking) with concrete schema.
- Reuse decisions from the audit's table stand — this doc doesn't relitigate what to keep vs. rebuild, only specifies how the "build" and "expand" items should be structured.