# Follei Systems 1–6 Completion Audit

Audited 2026-07-20 against the attached Version 1.0 proposal and the prior `SYSTEM_1_2_HANDOVER_2026-07-20.txt`. This audit scores the current backend repository and fresh local runtime. It does not treat the separate Vercel frontend as source code because that repository is not present here.

## Scope and scoring

The selected launch slice is **all System 1 capabilities + all System 2 capabilities + the complete Communication Layer + the Support Worker and its four responsibilities**. This is 80 of the proposal's 239 separately named capabilities.

Percentage formula: `sum(status points) / (4 × number of capabilities) × 100`. Percentages are truncated, never rounded up.

- 0 — no implementation of the named capability
- 1 — code/interface exists, but is untested, dormant, placeholder, or broken
- 2 — relevant automated test passed, but no real live provider/end-to-end proof
- 3 — fresh or retained live HTTP/DB/service evidence was re-verified
- 4 — production hardening proven, including retry/monitoring, backups/restore, and security review

No capability receives status 4. The repository has retries and health checks in places, but no demonstrated backup/restore drill, security review, production HA, or soak/load record.

## Fresh evidence catalog

| ID | Literal command/result |
|---|---|
| P1 | `GET http://127.0.0.1:8000/health/` → `{"status":"healthy","services":{"api":"ok","postgres":"ok","redis":"ok","qdrant":"ok","kafka":"ok","ferretdb":"ok","object_storage":"ok"},"queues":{"indexing":{"queued":0,"processing":0,"retrying":0,"failed":0,"dead_lettered":1},"knowledge_sync":{"pending":0,"processing":0,"retrying":0}}}` |
| P2 | `python -m pytest tests -q` → `192 passed, 185 warnings`; this is the configured main suite. |
| P3 | `python -m pytest app/services/mcp/tests -q` → `48 passed, 12 warnings`; all provider calls in these tests are mocked. |
| P4 | `python -m pytest app/services/ai/test_ai_service.py -q` → `19 passed, 9 failed`; failures are missing declared `Settings.AI_MODELS` and related loader initialization. |
| P5 | Tenant `ec495aee...`: `POST /chat/ {question:"What is the refund window?"}` → `HTTP 200`; literal response fields include `"duration": "45 days"`, `"supported":true`, `"confidence":0.7`, and citation sources `qdrant_chunk`, `postgres_fact`, `graph_relation`, `ferretdb_memory`. Four fresh questions also returned `USD 999`, `100` seats, and `2 hours`. |
| P6 | Tenant `ec495aee...`: `POST /channels/email/inbound` refund question → `HTTP 200`; literal fields: `"intent":"question","escalated":false`, reply `"duration": "45 days"`, `"confidence":0.7`, citations present. This proves the local webhook-to-Support-worker path, not external email delivery. |
| P7 | `POST /channels/email/inbound` human request → HTTP 200, `intent:"escalation_requested"`, `escalated:true`; PostgreSQL row → `status:"needs_human", channel:"email", escalation.reason:"explicit_human_request"`. |
| P8 | PostgreSQL query across live tenants → `documents_total 15`, including indexed DOCX, PDF/OCR, PPTX, EML, CSV, XLSX, TXT and website documents; `jobs_total 14`, with literal dispositions `new`, `duplicate`, `new_version`, plus one intentional `dead_lettered` retry case. |
| P9 | PostgreSQL fact query for tenant `ec495aee...` → approved `faq:1`, `plan:1`, `policy:1`, `pricing:1`; draft `faq:6`, `plan:4`, `policy:8`, `pricing:5`, `product:3`, `sales_process:2`, `service:12`, `support_process:1`. |
| P10 | PostgreSQL graph query → `relation_type:"defines", count:5`; chat P5 returned graph citation objects. Only `defines` is live for this tenant. |
| P11 | PostgreSQL retrieval log → three recent real queries, including refund queries at 6,333 ms and 6,434 ms. |
| P12 | FerretDB query → onboarding tenant memory plus conversation memory containing `Replacing Salesforce`, `Budget is $5000`, `Email follow-up`, and competitor `Salesforce`. |
| P13 | OpenAPI query → `path_count:120`, mounted launch routes include `/upload/`, `/chat/`, `/channels/email/inbound`, `/knowledge/websites/ingest`, `/knowledge/orchestrator/context`; `campaign_routes:[]`. |
| P14 | Communication health probe → email `Settings has no attribute BREVO_API_KEY`; SMS `Settings has no attribute TWILIO_ACCOUNT_SID`; WhatsApp `Settings has no attribute WHATSAPP_API_TOKEN`; voice `provider is not configured`. |
| P15 | Tenant `ec495aee...` approval recheck → pricing/policy/plan/FAQ source chunks have literal PostgreSQL tags `['category:policy', 'approval:approved']`; outbox deliveries are `{'postgres':'completed','qdrant':'completed'}`. Event `f6c64658...` is `completed`, `attempt_count:6`. |
| P16 | Approved-only probe on tenant `ec495aee...` → draft phrase BM25 `[]`; neighbour expansion `[]`; Qdrant approved set `contains_draft_phrase:false`, statuses `["approved"]`. |
| P17 | Required handover tenant `87e38dbc...`: fresh `POST /chat/` → `HTTP 200` but literal answer `"The retrieved documents do not contain this information."`; orchestrator returned `"approved":[]` and `"evidence":[]`. Its approved draft payload says 45 days, but operational policy is `title='Documented policy', body=None` and source chunk still has `['category:policy','approval:draft']`; direct BM25 and dense output are both `[]`. |

### Literal chat outputs used for the status-3 decision

Working validation tenant, fresh HTTP projection of the response (the projection command prints the complete answer plus every returned citation-source type):

```text
{"http_status": 200, "answer": "```json\n{\n  \"answer\": {\n    \"refund_window\": {\n      \"duration\": \"45 days from the original purchase date\",\n      \"source\": [\n        \"follei-validation.txt (Section 4: Refund Policy, Table and Paragraph)\",\n        \"APPROVED BUSINESS FACTS (policy: Refund Policy)\",\n        \"APPROVED BUSINESS FACTS (faq: How long do I have to request a refund?)\"\n      ]\n    }\n  },\n  \"requirements\": {\n    \"required_identifier\": \"original order reference (must correspond to the subscription or purchase)\",\n    \"source\": [\n      \"follei-validation.txt (Section 4: Refund Policy, Table)\"\n    ]\n  }\n}\n```", "citation_sources": ["ferretdb_memory", "graph_relation", "postgres_fact", "qdrant_chunk"], "confidence": 0.7, "supported": true, "conflicts": []}
```

Required handover tenant, fresh full HTTP response:

```text
HTTP 200
{"answer":"```\n{\n  \"refund_window\": \"The retrieved documents do not contain this information.\"\n}\n```","citations":[{"source":"graph_relation","from":"refund_policy.docx","relation":"defines","to":"policy","citation":{"document_id":"fa8ad941-66da-4a8f-92bc-405214ddfd6d","document_name":"refund_policy.docx","chunk_id":"7b60bb2d-4707-4b52-ab63-cc37a40567ed","page":0,"heading":null,"heading_path":[],"source_uri":"verification://refund-policy","version":1},"trust_rank":2}],"confidence":0.7,"supported":true,"reason":"Grounded answer produced from retrieved context; LLM verification disabled for the fast path.","conversation_id":"4bfc6f46-dad2-4e50-8d4c-8afe277046c9","conflicts":[]}
```

## System 1 — Business Intelligence System

| ID | Launch | Capability | Status | Evidence / strict reason |
|---|---:|---|---:|---|
| S1.01 | Y | Website source | 3 | Safe Vercel crawl and Kafka indexing re-verified in P1/P8; SSRF/robots/limits tests in P2. |
| S1.02 | Y | PDF source | 3 | Indexed scanned PDF rows and OCR text exist in P8; PDF tests pass in P2. |
| S1.03 | Y | Brochures | 2 | Generic PDF/DOCX loaders and classifier tests pass, but no identified brochure was live-run. |
| S1.04 | Y | Product Catalogs | 2 | Catalog classifier/chunker tests pass in P2; no current live product-catalog proof. |
| S1.05 | Y | SOPs | 2 | SOP classifier test passes in P2; no identified SOP live proof. |
| S1.06 | Y | Sales Decks | 3 | `follei-live-proof.pptx` is indexed in P8; PPTX loader test passes. |
| S1.07 | Y | Pricing Sheets | 3 | Live validation pricing and XLSX document are indexed; approved pricing record is cited in P5/P8/P9. |
| S1.08 | Y | Google Drive connector | 2 | Real HTTP/OAuth-shaped code and mocked tests pass in P3; no real OAuth/provider run. |
| S1.09 | Y | Microsoft OneDrive connector | 0 | No OneDrive connector or Graph Drive implementation found. |
| S1.10 | Y | SharePoint connector | 0 | No SharePoint implementation found. |
| S1.11 | Y | Notion connector | 0 | No Notion implementation found. |
| S1.12 | Y | Confluence connector | 0 | No Confluence implementation found. |
| S1.13 | Y | Gmail connector | 2 | Gmail HTTP/OAuth code and mocked tests pass in P3; no live Gmail account connection. |
| S1.14 | Y | Outlook connector | 2 | Outlook Graph/OAuth code and mocked tests pass in P3; no live Microsoft account. |
| S1.15 | Y | WhatsApp source connector | 2 | Meta API-shaped MCP code and mocked tests pass in P3; live settings/provider path fails P14. |
| S1.16 | Y | Teams connector | 2 | Connector code and mocked MCP tests pass in P3; no tenant OAuth/live Teams proof. |
| S1.17 | Y | Slack connector | 2 | Connector tests pass in P3 but service explicitly supports mock fallback; no live Slack workspace. |
| S1.18 | Y | CRM connector | 2 | HubSpot/Salesforce/Zoho mocked MCP tests pass P3; legacy CRM base methods also contain `NotImplementedError`; no real CRM OAuth. |
| S1.19 | Y | ERP connector | 2 | ERP adapter/mock tests pass P3; no live SAP/Odoo/Oracle/Dynamics account. |
| S1.20 | Y | LMS connector | 0 | No LMS connector implementation found. |
| S1.21 | Y | Accounting Software connector | 0 | No accounting connector implementation found. |
| S1.22 | Y | Ticketing Platform connector | 0 | No ticketing connector implementation found. |
| S1.23 | Y | Extract Products | 3 | Live `product` drafts in P9; schema/extraction/publisher tests pass P2. |
| S1.24 | Y | Extract Services | 3 | Live `service` drafts in P9; schema/extraction/publisher tests pass P2. |
| S1.25 | Y | Extract Pricing | 3 | Approved live pricing record and chat citation in P5/P9/P15. |
| S1.26 | Y | Extract Plans | 3 | Approved live plan record in P9/P15. |
| S1.27 | Y | Extract Policies | 3 | Approved live refund policy and grounded chat answer in P5/P9/P15. |
| S1.28 | Y | Extract FAQs | 3 | Approved live FAQ and grounded chat/Support responses in P5/P6/P9. |
| S1.29 | Y | Extract Competitors | 2 | Deterministic extraction/schema/publisher test passes; no live `competitor` fact draft in P9. |
| S1.30 | Y | Extract Customer Segments | 2 | Deterministic extraction/schema/publisher test passes; no live `customer_segment` fact draft. |
| S1.31 | Y | Extract Sales Processes | 3 | Live `sales_process` drafts in P9; publisher test passes. |
| S1.32 | Y | Extract Support Processes | 3 | Live `support_process` draft in P9; publisher test passes. |
| S1.33 | Y | Extract Payment Processes | 2 | Deterministic extraction/schema/publisher test passes; no live `payment_process` draft. |
| S1.34 | Y | Business Knowledge Graph output | 3 | Five live `defines` relations and explicit graph chat citations in P5/P10. |

System 1 subtotal: **67 / 136 points = 49.26%**.

## System 2 — Knowledge System

| ID | Launch | Capability | Status | Evidence / strict reason |
|---|---:|---|---:|---|
| S2.01 | Y | Structured store: Products | 2 | Operational model/publisher tests pass; live tenant currently has product drafts, not an approved product record. |
| S2.02 | Y | Structured store: Services | 2 | Operational model/publisher tests pass; live tenant currently has service drafts, not an approved service record. |
| S2.03 | Y | Structured store: Pricing | 3 | Live approved `pricing_models` record and chat citation P5/P9/P15. |
| S2.04 | Y | Structured store: Policies | 3 | Live approved policy record and chat citation P5/P9/P15. |
| S2.05 | Y | Structured store: Plans | 3 | Live approved business plan P9/P15. |
| S2.06 | Y | Structured store: SLAs | 2 | Plan/pricing schema supports response targets and tests pass; no dedicated live approved SLA record/table proof. |
| S2.07 | Y | Vector store: Documents | 3 | Qdrant health and cited approved document chunks P1/P5/P15. |
| S2.08 | Y | Vector store: Emails | 3 | Live indexed EML document in P8. |
| S2.09 | Y | Vector store: PDFs | 3 | Live indexed/OCR PDF rows in P8. |
| S2.10 | Y | Vector store: Call Transcripts | 2 | Turn-aware call chunker test passes; no live call transcript vector row. |
| S2.11 | Y | Vector store: Knowledge Articles | 2 | Generic text/document indexing tests pass; no source explicitly proven as a knowledge article. |
| S2.12 | Y | Semantic retrieval | 3 | Live Qdrant retrieval, hybrid chat, citations, approval filter and telemetry P5/P11/P16. |
| S2.13 | Y | Graph: Product → Feature | 2 | `has_feature` graph test passes; only `defines` is live in P10. |
| S2.14 | Y | Graph: Feature → Benefit | 0 | No implementation of this edge; current graph links primary fact directly to features/benefits. |
| S2.15 | Y | Graph: Benefit → Customer Segment | 0 | No implementation of this edge. |
| S2.16 | Y | Graph: Customer Segment → Objections | 1 | Generic objection relation code exists, but no specific automated or live segment-objection proof. |
| S2.17 | Y | Graph: Objections → Responses | 0 | No response-node/edge implementation found. |
| S2.18 | Y | Long-Term Memory: company knowledge | 3 | Approved PostgreSQL/Qdrant/graph company knowledge live P5/P9/P10/P15. |
| S2.19 | Y | Mid-Term Memory: customer history | 3 | FerretDB conversation memory live P12. |
| S2.20 | Y | Short-Term Memory: active conversation context | 3 | Live chat/support conversations and persisted conversation IDs P5–P7. |

System 2 subtotal: **43 / 80 points = 53.75%**.

## System 3 — Revenue Intelligence System

| ID | Launch | Capability | Status | Evidence / strict reason |
|---|---:|---|---:|---|
| S3.01 | N | Lead Intelligence Engine | 1 | Models/services exist, but mounted lead routes return in-memory fixed scores and the scoring worker contains unfinished logic. |
| S3.02 | N | ICP Score | 1 | Field/scoring code exists; no passing dedicated test or live calculated score. |
| S3.03 | N | Intent Score | 1 | Field/scoring code exists; no passing dedicated test or live calculated score. |
| S3.04 | N | Engagement Score | 1 | Field/scoring code exists; no passing dedicated test or live calculated score. |
| S3.05 | N | Qualification Score | 1 | Field/scoring code exists; no passing dedicated test or live calculated score. |
| S3.06 | N | Buying Signal Score | 1 | Field/scoring code exists; no passing dedicated test or live calculated score. |
| S3.07 | N | Relationship Score | 1 | Field/scoring code exists; no passing dedicated test or live calculated score. |
| S3.08 | N | Qualification Framework Engine | 1 | Service contracts exist but are not part of a proven mounted workflow. |
| S3.09 | N | BANT | 1 | BANT-shaped service code exists; no passing test or live qualification run. |
| S3.10 | N | MEDDIC | 1 | MEDDIC-shaped service code exists; no passing test or live qualification run. |
| S3.11 | N | SPIN | 0 | No SPIN implementation found. |
| S3.12 | N | CHAMP | 0 | No CHAMP implementation found. |
| S3.13 | N | ANUM | 0 | No ANUM implementation found. |
| S3.14 | N | Custom Frameworks | 1 | In-memory framework CRUD/schema code exists; no durable, tested engine. |
| S3.15 | N | Industry-specific qualification frameworks | 1 | Configuration hooks exist, but no concrete tested industry framework. |
| S3.16 | N | Revenue Probability Engine | 1 | Model/service references exist; no tested or live prediction pipeline. |
| S3.17 | N | Probability of conversion | 1 | Output field exists; no proven model inference. |
| S3.18 | N | Historical deals as an input | 1 | Schema/query references exist; no proven feature pipeline. |
| S3.19 | N | Behavioral data as an input | 1 | Schema references exist; no proven feature pipeline. |
| S3.20 | N | Intent signals as an input | 1 | Schema references exist; no proven feature pipeline. |
| S3.21 | N | Qualification data as an input | 1 | Schema references exist; no proven feature pipeline. |
| S3.22 | N | Revenue Probability Score (0–100) | 1 | Response/model field exists; no passing calculation test or live output. |

System 3 subtotal: **19 / 88 points = 21.59%**.

## System 4 — Customer Intelligence System

| ID | Launch | Capability | Status | Evidence / strict reason |
|---|---:|---|---:|---|
| S4.01 | N | Customer Health Engine | 1 | Customer routes/models contain health values, but mounted routes use fixed in-memory scores. |
| S4.02 | N | Product Adoption measure | 1 | Event/model fields exist; no tested health calculation. |
| S4.03 | N | Feature Usage measure | 1 | Event/model fields exist; no tested health calculation. |
| S4.04 | N | Engagement measure | 1 | Event/model fields exist; no tested health calculation. |
| S4.05 | N | Satisfaction measure | 1 | Field/reference exists; no tested health calculation. |
| S4.06 | N | Churn Prediction Engine | 1 | Model/service references exist; no passing prediction test or live inference. |
| S4.07 | N | Detect usage decline | 0 | No operational detector found. |
| S4.08 | N | Detect support escalation | 0 | Support escalation works, but no churn-engine signal integration exists. |
| S4.09 | N | Detect payment delays | 0 | No operational detector found. |
| S4.10 | N | Detect negative sentiment | 1 | Sentiment analysis code exists, but it is not wired into a churn detector. |
| S4.11 | N | Churn Risk Score | 1 | Field/fixed response exists; no proven calculation. |
| S4.12 | N | Expansion Engine | 1 | Model/service references exist; no tested opportunity engine. |
| S4.13 | N | Detect upsell opportunities | 0 | No operational detector found. |
| S4.14 | N | Detect cross-sell opportunities | 0 | No operational detector found. |
| S4.15 | N | Detect renewal opportunities | 1 | In-memory renewal CRUD exists; no detection workflow. |
| S4.16 | N | Expansion Probability Score | 1 | Field exists; no proven calculation. |

System 4 subtotal: **11 / 64 points = 17.18%**.

## System 5 — AI Workforce System

| ID | Launch | Capability | Status | Evidence / strict reason |
|---|---:|---|---:|---|
| S5.01 | N | SDR Worker | 1 | Agent/tool contracts exist; no complete worker or live run. |
| S5.02 | N | SDR: lead qualification | 1 | Qualification service references exist; no worker test/live proof. |
| S5.03 | N | SDR: lead nurturing | 1 | Campaign/task references exist; no worker test/live proof. |
| S5.04 | N | SDR: discovery conversations | 0 | No complete implementation found. |
| S5.05 | N | SDR: meeting booking | 1 | Calendar/tool contracts exist; no worker test/live provider run. |
| S5.06 | N | SDR channel: Voice | 1 | Provider interface/stub exists; no delivery. |
| S5.07 | N | SDR channel: WhatsApp | 1 | Provider/tool code exists; no SDR workflow or live delivery. |
| S5.08 | N | SDR channel: Email | 1 | Provider/tool code exists; no SDR workflow or live delivery. |
| S5.09 | N | Sales Executive Worker | 1 | Agent contracts exist; no complete worker. |
| S5.10 | N | Sales: product explanation | 1 | Knowledge context could support it, but no tested Sales worker. |
| S5.11 | N | Sales: objection handling | 0 | No complete implementation found. |
| S5.12 | N | Sales: proposal generation | 1 | Schema/service references exist; no passing workflow test. |
| S5.13 | N | Sales: deal progression | 1 | Deal/tool references exist; no passing workflow test. |
| S5.14 | N | Customer Success Worker | 1 | Agent contract exists; no complete worker. |
| S5.15 | N | Customer Success: onboarding | 1 | Human onboarding API is live, but no autonomous CS-worker workflow. |
| S5.16 | N | Customer Success: adoption | 0 | No complete worker implementation found. |
| S5.17 | N | Customer Success: engagement | 0 | No complete worker implementation found. |
| S5.18 | N | Customer Success: renewal preparation | 1 | Renewal/tool references exist; no worker test/live run. |
| S5.19 | Y | Support Worker | 3 | Live inbound webhook invokes Support worker and returns grounded answers P6. |
| S5.20 | Y | Support: customer support | 3 | Live refund request handled with tenant-scoped grounded context P6. |
| S5.21 | Y | Support: FAQ handling | 3 | Live 45-day FAQ/policy answer with citations P6. |
| S5.22 | Y | Support: ticket resolution | 1 | Conversation/escalation records exist, but no complete ticketing-provider resolution loop. |
| S5.23 | Y | Support: escalation management | 3 | Explicit human request produced `needs_human` PostgreSQL state P7. |
| S5.24 | N | Collections Worker | 1 | Contract/schema references exist; no complete worker. |
| S5.25 | N | Collections: payment reminders | 0 | No complete implementation found. |
| S5.26 | N | Collections: invoice follow-up | 0 | No complete implementation found. |
| S5.27 | N | Collections: collection calls | 0 | No complete implementation found. |
| S5.28 | N | Collections: renewal reminders | 0 | No complete implementation found. |
| S5.29 | N | Account Manager Worker | 1 | Contract/schema references exist; no complete worker. |
| S5.30 | N | Account Manager: relationship management | 0 | No complete implementation found. |
| S5.31 | N | Account Manager: expansion opportunities | 0 | No complete implementation found. |
| S5.32 | N | Account Manager: executive communication | 0 | No complete implementation found. |
| S5.33 | N | Executive Insights Worker | 1 | Agent/dashboard references exist; no complete worker. |
| S5.34 | N | Leadership dashboards and recommendations | 1 | In-memory analytics response code exists; no proven insights worker. |
| S5.35 | N | Detect reduced revenue forecast | 0 | No complete implementation found. |
| S5.36 | N | Explain stalled opportunities | 0 | No complete implementation found. |
| S5.37 | N | Recommend executive intervention | 0 | No complete implementation found. |

System 5 subtotal: **31 / 148 points = 20.94%**.

## System 6 — Learning System

| ID | Launch | Capability | Status | Evidence / strict reason |
|---|---:|---|---:|---|
| S6.01 | N | Continuous Learning System | 0 | No end-to-end learning system found. |
| S6.02 | N | Learning loop: Action capture | 1 | Interaction/action records exist, but not a complete learning loop. |
| S6.03 | N | Learning loop: Customer Response capture | 1 | Conversation records exist, but not a complete learning loop. |
| S6.04 | N | Learning loop: Outcome capture | 1 | Outcome fields/references exist, but no proven evaluator. |
| S6.05 | N | Learning loop: Performance Measurement | 1 | Metric schemas/references exist; no proven feedback computation. |
| S6.06 | N | Learning loop: Model Update | 1 | Training/update hooks are referenced, but no tested update pipeline. |
| S6.07 | N | Call → meeting booked → positive signal | 0 | No complete implementation found. |
| S6.08 | N | Proposal → closed won → positive signal | 0 | No complete implementation found. |
| S6.09 | N | Support ticket → escalated → negative signal | 0 | Escalation is stored, but no learning-signal pipeline exists. |
| S6.10 | N | Learn from every interaction | 0 | No operational model-improvement loop exists. |

System 6 subtotal: **5 / 40 points = 12.50%**.

## Communication Layer

| ID | Launch | Capability | Status | Evidence / strict reason |
|---|---:|---|---:|---|
| C.01 | Y | Voice channel | 1 | Interface/provider stub exists; health probe says provider is not configured P14. |
| C.02 | Y | Inbound Calls | 1 | Route/provider concepts exist; no real number/provider/live call. |
| C.03 | Y | Outbound Calls | 1 | Provider interface exists; no real delivery. |
| C.04 | Y | AI Receptionist | 0 | No complete receptionist implementation found. |
| C.05 | Y | WhatsApp channel | 2 | Meta API-shaped code and mocked MCP tests pass P3; live provider settings fail P14. |
| C.06 | Y | WhatsApp messages | 2 | Send/read tool tests pass with mocks P3; no real delivery receipt. |
| C.07 | Y | WhatsApp voice notes | 1 | Media/message fields exist; no passing voice-note workflow test. |
| C.08 | Y | WhatsApp documents | 2 | Attachment/tool handling has mocked tests P3; no real delivery. |
| C.09 | Y | WhatsApp media | 2 | Media/tool handling has mocked tests P3; no real delivery. |
| C.10 | Y | Email channel | 2 | Inbound Support endpoint and provider unit paths exist; no real outbound delivery, and provider settings fail P14. |
| C.11 | Y | Email outbound campaigns | 1 | Campaign API code is not mounted and campaign worker `_process` is unfinished; no send proof P13/P14. |
| C.12 | Y | Email automated responses | 3 | Live email-shaped inbound webhook generated a grounded automated response P6; this does not prove external sending. |
| C.13 | Y | Email personalized follow-ups | 1 | Templates/task code exists; no complete tested/delivered follow-up. |
| C.14 | Y | SMS channel | 1 | Twilio-shaped provider code exists; runtime settings are absent P14. |
| C.15 | Y | SMS reminders | 1 | Reminder/task references exist; no tested delivery workflow. |
| C.16 | Y | SMS alerts | 1 | Alert/task references exist; no tested delivery workflow. |
| C.17 | Y | SMS notifications | 1 | Notification/task references exist; no tested delivery workflow. |
| C.18 | Y | Website Chat | 3 | Real `/chat/` HTTP response is grounded and cited P5. |
| C.19 | Y | Website Chat: lead capture | 1 | Lead CRUD/schema exists, but no tested chat-to-lead workflow. |
| C.20 | Y | Website Chat: support | 3 | Grounded chat and Support webhook work live P5/P6. |
| C.21 | Y | Website Chat: qualification | 1 | Qualification code exists, but no tested chat qualification workflow. |

Communication subtotal: **31 / 84 points = 36.90%**.

## AI Models

| ID | Launch | Capability | Status | Evidence / strict reason |
|---|---:|---|---:|---|
| A.01 | N | Intent Detection | 3 | Live Support calls classified `question` and `escalation_requested` P6/P7. |
| A.02 | N | Sentiment Analysis | 2 | Conversation analysis tests pass in P2; no live response/DB field captured in this audit. |
| A.03 | N | Topic Classification | 3 | Live documents received categories and classifier/chunker tests pass P2/P8. |
| A.04 | N | Objection Detection | 0 | No operational detector found. |
| A.05 | N | Entity Extraction | 3 | Live FerretDB entities include budget, preference and competitor P12. |
| A.06 | N | Speech-to-Text | 1 | Loader/provider code exists; excluded AI suite fails and no live inference P4. |
| A.07 | N | Text-to-Speech | 1 | Loader/provider code exists; excluded AI suite fails and no live inference P4. |
| A.08 | N | Voice Cloning | 0 | No implementation found. |
| A.09 | N | Emotion Detection | 1 | Model-loader references exist; no passing test/live inference P4. |
| A.10 | N | ML: Lead Scoring | 1 | Service/model references exist; no passing/live model calculation. |
| A.11 | N | ML: Conversion Prediction | 1 | Service/model references exist; no passing/live model calculation. |
| A.12 | N | ML: Deal Risk Prediction | 0 | No operational prediction implementation found. |
| A.13 | N | ML: Churn Prediction | 1 | Service/model references exist; no passing/live model calculation. |
| A.14 | N | ML: Upsell Prediction | 0 | No operational prediction implementation found. |
| A.15 | N | ML: Payment Risk Prediction | 0 | No operational prediction implementation found. |
| A.16 | N | ML: Revenue Forecasting | 0 | No operational model implementation found. |
| A.17 | N | Multi-Agent Orchestration | 1 | Agent contracts/registry code exist; most workers are absent and no multi-agent live run exists. |
| A.18 | N | Planning | 1 | Planner/task schemas exist; no passing planner test or live run. |
| A.19 | N | Task Execution | 2 | MCP executor/tool tests pass with mocked providers P3; no real-provider task execution. |
| A.20 | N | Reasoning | 3 | Live RAG answer synthesis and conflict-aware context run P5. |
| A.21 | N | Tool Usage | 2 | MCP tool tests pass with mocks P3; providers are not live. |
| A.22 | N | Memory Management | 3 | Live PostgreSQL/Qdrant/FerretDB context composition P5/P12. |

AI Models subtotal: **29 / 88 points = 32.95%**.

## Analytics Layer

| ID | Launch | Capability | Status | Evidence / strict reason |
|---|---:|---|---:|---|
| AN.01 | N | Revenue Analytics: Pipeline Value | 0 | No operational calculation found. |
| AN.02 | N | Revenue Analytics: Forecast Revenue | 0 | No operational calculation found. |
| AN.03 | N | Revenue Analytics: Sales Velocity | 0 | No operational calculation found. |
| AN.04 | N | Revenue Analytics: Win Rate | 0 | No operational calculation found. |
| AN.05 | N | Revenue Analytics: AI Generated Revenue | 0 | No operational attribution calculation found. |
| AN.06 | N | Customer Analytics: Customer Health | 1 | Fixed/in-memory response field exists; no tested calculation. |
| AN.07 | N | Customer Analytics: Retention | 0 | No operational calculation found. |
| AN.08 | N | Customer Analytics: Renewal Rate | 0 | No operational calculation found. |
| AN.09 | N | Customer Analytics: Churn | 1 | Field/model reference exists; no tested calculation. |
| AN.10 | N | Operations Analytics: Response Time | 1 | Metric field/reference exists; no proven analytics computation. |
| AN.11 | N | Operations Analytics: Resolution Time | 1 | Metric field/reference exists; no proven analytics computation. |
| AN.12 | N | Operations Analytics: Agent Utilization | 1 | Metric field/reference exists; no proven analytics computation. |
| AN.13 | N | Operations Analytics: Automation Rate | 1 | Metric field/reference exists; no proven analytics computation. |

Analytics subtotal: **6 / 52 points = 11.53%**.

## Industry Adaptation Framework

| ID | Launch | Capability | Status | Evidence / strict reason |
|---|---:|---|---:|---|
| I.01 | N | Industry Pack Architecture | 0 | No pack/plugin architecture implementing these industry workflows found. |
| I.02 | N | Education Pack | 0 | No implementation found. |
| I.03 | N | Education: Admissions | 0 | No implementation found. |
| I.04 | N | Education: Counselling | 0 | No implementation found. |
| I.05 | N | Education: Fee Collection | 0 | No implementation found. |
| I.06 | N | Education: Student Success | 0 | No implementation found. |
| I.07 | N | Healthcare Pack | 0 | No implementation found. |
| I.08 | N | Healthcare: Appointments | 0 | No implementation found. |
| I.09 | N | Healthcare: Patient Follow-up | 0 | No implementation found. |
| I.10 | N | Healthcare: Care Plans | 0 | No implementation found. |
| I.11 | N | Healthcare: Billing | 0 | No implementation found. |
| I.12 | N | Real Estate Pack | 0 | No implementation found. |
| I.13 | N | Real Estate: Property Discovery | 0 | No implementation found. |
| I.14 | N | Real Estate: Site Visits | 0 | No implementation found. |
| I.15 | N | Real Estate: Booking Follow-up | 0 | No implementation found. |
| I.16 | N | Real Estate: Documentation | 0 | No implementation found. |
| I.17 | N | Manufacturing Pack | 0 | No implementation found. |
| I.18 | N | Manufacturing: Procurement | 0 | No implementation found. |
| I.19 | N | Manufacturing: Vendor Discussions | 0 | No implementation found. |
| I.20 | N | Manufacturing: Compliance | 0 | No implementation found. |
| I.21 | N | Manufacturing: Implementation Planning | 0 | No implementation found. |

Industry adaptation subtotal: **0 / 84 points = 0.00%**.

## Technology Architecture

| ID | Launch | Capability | Status | Evidence / strict reason |
|---|---:|---|---:|---|
| T.01 | N | Frontend: React / Next.js | 0 | The audited repository contains no frontend source. The hosted Vercel UI is not evidence that this repository implements or connects it. |
| T.02 | N | Backend: Python FastAPI | 3 | Live FastAPI OpenAPI/health/chat endpoints P1/P5/P13. |
| T.03 | N | Workflows: Temporal | 0 | No Temporal integration found. |
| T.04 | N | Database: PostgreSQL | 3 | Live health and operational rows P1/P7–P11/P15. |
| T.05 | N | Analytics: ClickHouse | 0 | No ClickHouse implementation found. |
| T.06 | N | Caching: Redis | 3 | Live health P1. |
| T.07 | N | Vector Database: Qdrant | 3 | Live health, retrieval, approval sync and filtering P1/P5/P15/P16. |
| T.08 | N | Object Storage: S3-compatible | 3 | Live object-storage health and MinIO object key P1/P8. |
| T.09 | N | AI Models: OpenAI | 0 | No operational OpenAI provider path found in the audited runtime. |
| T.10 | N | AI Models: Claude | 1 | Unmounted/dormant provider references exist; no passing/live inference. |
| T.11 | N | AI Models: Open-source models | 1 | Loader code exists, but its excluded test suite has nine failures P4. |
| T.12 | N | ML Stack: PyTorch | 1 | Dependency/loader references exist; no passing model pipeline. |
| T.13 | N | ML Stack: XGBoost | 1 | Dependency/model references exist; no passing model pipeline. |
| T.14 | N | ML Stack: LightGBM | 0 | No implementation found. |
| T.15 | Y | Communications: Twilio | 1 | Twilio-shaped SMS code exists, but runtime settings are absent P14. |
| T.16 | Y | Communications: WhatsApp Business API | 2 | Meta API-shaped code and mocked tests pass P3; no real account/delivery. |
| T.17 | Y | Communications: SendGrid | 0 | No SendGrid implementation found; incomplete Brevo code is present instead. |

Technology subtotal: **22 / 68 points = 32.35%**.

## North Star Metric

| ID | Launch | Capability | Status | Evidence / strict reason |
|---|---:|---|---:|---|
| N.01 | N | Revenue Influence Score | 0 | No calculation/attribution implementation found. |
| N.02 | N | Revenue influenced through Sales | 0 | No attribution implementation found. |
| N.03 | N | Revenue influenced through Support | 0 | Support works locally, but no revenue attribution exists. |
| N.04 | N | Revenue influenced through Renewals | 0 | No attribution implementation found. |
| N.05 | N | Revenue influenced through Collections | 0 | No attribution implementation found. |
| N.06 | N | Revenue influenced through Upsells | 0 | No attribution implementation found. |

North Star subtotal: **0 / 24 points = 0.00%**.

## Strict completion result

The launch slice contains the 34 System 1 rows, 20 System 2 rows, 21 Communication rows, and the five Support-worker rows S5.19–S5.23: **80 capabilities** total.

| Scope | Earned points | Maximum | Strict completion |
|---|---:|---:|---:|
| Launch slice: Systems 1–2 + all communications + Support worker | 154 | 320 | **48.12%** |
| Full proposal as written | 264 | 956 | **27.61%** |

These are maturity-weighted percentages, not counts of files or routes. A capability that is merely coded earns 1/4; passing tests earn 2/4; a fresh live proof earns 3/4. No item earns 4 because this audit found no provider-complete retry/monitoring/backup/security-review evidence sufficient for production hardening.

Status distribution:

| Scope | Status 0 | Status 1 | Status 2 | Status 3 | Status 4 |
|---|---:|---:|---:|---:|---:|
| Launch slice (80) | 11 | 14 | 25 | 30 | 0 |
| Full proposal (239) | 84 | 86 | 29 | 40 | 0 |

## What is actually launch-ready, and what is not

The strongest working slice is tenant-scoped document/web ingestion into PostgreSQL, object storage and Qdrant; fact draft review/approval; outbox-driven Qdrant approval synchronization; approved-only hybrid retrieval; graph/FerretDB context; grounded `/chat/`; and the local inbound-email-shaped Support worker with human escalation. Those paths have fresh HTTP/database/vector evidence.

The requested communications launch is **not ready**. Outbound campaign routes are not mounted, the campaign worker does not process sends, email/SMS/WhatsApp runtime configuration is discarded or absent, voice is a stub, and there is no external-provider delivery receipt. P6 proves an inbound webhook-shaped request and generated answer only; it does not prove an email reached a mailbox.

The application is also not production-hardened. There is one dead-lettered indexing job, no audited backup/restore exercise, no high-availability/failover proof, no load/soak result, and no documented security review. Provider credentials appeared in local command output during this audit and must be rotated; this report does not reproduce them.

There is also a tenant-specific correctness regression that blocks a blanket “System 1/2 finished” claim. The newer validation tenant works P5/P15, but the handover's required refund tenant does not P17. Its fact was marked approved while its operational policy lost the body and its source chunk remained draft, so approved-only retrieval correctly excludes it. This is a real migration/backfill or approval-path consistency problem, not an LLM-quality issue.

## Prior handover claims: re-verification result

| Prior claim | Audit result |
|---|---|
| Main suite is green at 192 tests | **Re-verified**, P2. But the handover omitted the separately located MCP suite and AI suite. MCP adds 48 mocked passes P3; AI has 9 failures P4. |
| Kafka and all listed infrastructure are healthy | **Re-verified at health level**, P1. This does not prove production durability. One indexing job remains dead-lettered. |
| CSV, XLSX, PPTX, EML, OCR PDF and website ingest work | **Re-verified as live indexed rows** across the validation tenants, P8. Legacy binary `.ppt`, `.msg` attachments, OCR accuracy at scale, and arbitrary-site crawl compatibility remain unproven. |
| All extraction categories are complete | **Not re-verified live.** Unit/publisher coverage exists for the eleven current fact types, but current live rows cover only eight; competitor, customer segment and payment process lack live extracted rows P9. |
| Fact approval always synchronizes PostgreSQL and Qdrant | **Partly re-verified, partly contradicted.** The validation tenant is synchronized P15; the handover's required tenant is inconsistent P17. |
| Refund-window chat works for tenant `87e38dbc...` | **Contradicted by fresh run.** Literal current answer says the information is absent P17. A different validation tenant answers correctly P5. |
| Approved-only retrieval works | **Re-verified for synchronized validation data**, P16. The stale tenant is excluded because its chunk is still draft, exposing the sync gap rather than leaking draft content. |
| Graph citations are returned | **Re-verified**, P5/P10, but only the generic `defines` edge is live; the proposal's full relationship chain is not implemented. |
| FerretDB onboarding/conversation memory works | **Re-verified**, P12. |
| Retrieval telemetry is persisted | **Re-verified**, P11. |
| Shared context is ready for every worker | **Overstated.** A shared contract and tests exist, but most actual worker implementations do not. Only Support is live. |
| Campaigns/Brevo delivery is ready or merely deferred | **Not working in the current runtime.** Campaign routes are unmounted, worker processing is unfinished, and provider settings fail P13/P14. |
| Systems 1 and 2 are roughly 94%/90% | **Not supported under the requested 0–4 rubric.** Strict scores are 49.26% and 53.75%; the combined launch slice with communications and Support is 48.12%. |

## Every capability still at status 0

- **System 1:** S1.09 Microsoft OneDrive connector; S1.10 SharePoint connector; S1.11 Notion connector; S1.12 Confluence connector; S1.20 LMS connector; S1.21 Accounting Software connector; S1.22 Ticketing Platform connector.

- **System 2:** S2.14 Graph Feature → Benefit; S2.15 Graph Benefit → Customer Segment; S2.17 Graph Objections → Responses.

- **System 3:** S3.11 SPIN; S3.12 CHAMP; S3.13 ANUM.

- **System 4:** S4.07 Detect usage decline; S4.08 Detect support escalation as a churn signal; S4.09 Detect payment delays; S4.13 Detect upsell opportunities; S4.14 Detect cross-sell opportunities.

- **System 5:** S5.04 SDR discovery conversations; S5.11 Sales objection handling; S5.16 Customer Success adoption; S5.17 Customer Success engagement; S5.25 Collections payment reminders; S5.26 Collections invoice follow-up; S5.27 Collections calls; S5.28 Collections renewal reminders; S5.30 Account Manager relationship management; S5.31 Account Manager expansion opportunities; S5.32 Account Manager executive communication; S5.35 detect reduced revenue forecast; S5.36 explain stalled opportunities; S5.37 recommend executive intervention.

- **System 6:** S6.01 Continuous Learning System; S6.07 call → meeting → positive signal; S6.08 proposal → closed won → positive signal; S6.09 Support escalation → negative learning signal; S6.10 learn from every interaction.

- **Communications:** C.04 AI Receptionist.

- **AI models:** A.04 Objection Detection; A.08 Voice Cloning; A.12 Deal Risk Prediction; A.14 Upsell Prediction; A.15 Payment Risk Prediction; A.16 Revenue Forecasting.

- **Analytics:** AN.01 Pipeline Value; AN.02 Forecast Revenue; AN.03 Sales Velocity; AN.04 Win Rate; AN.05 AI Generated Revenue; AN.07 Retention; AN.08 Renewal Rate.

- **Industry adaptation:** I.01 Industry Pack Architecture; I.02 Education Pack; I.03 Admissions; I.04 Counselling; I.05 Fee Collection; I.06 Student Success; I.07 Healthcare Pack; I.08 Appointments; I.09 Patient Follow-up; I.10 Care Plans; I.11 Billing; I.12 Real Estate Pack; I.13 Property Discovery; I.14 Site Visits; I.15 Booking Follow-up; I.16 Documentation; I.17 Manufacturing Pack; I.18 Procurement; I.19 Vendor Discussions; I.20 Compliance; I.21 Implementation Planning.

- **Technology:** T.01 Frontend React/Next.js in this repository; T.03 Temporal; T.05 ClickHouse; T.09 OpenAI provider; T.14 LightGBM; T.17 SendGrid.

- **North Star:** N.01 Revenue Influence Score; N.02 Sales attribution; N.03 Support attribution; N.04 Renewals attribution; N.05 Collections attribution; N.06 Upsells attribution.

## Every capability still at status 1

- **System 2:** S2.16 Graph Customer Segment → Objections.

- **System 3:** S3.01 Lead Intelligence Engine; S3.02 ICP Score; S3.03 Intent Score; S3.04 Engagement Score; S3.05 Qualification Score; S3.06 Buying Signal Score; S3.07 Relationship Score; S3.08 Qualification Framework Engine; S3.09 BANT; S3.10 MEDDIC; S3.14 Custom Frameworks; S3.15 industry-specific qualification frameworks; S3.16 Revenue Probability Engine; S3.17 probability of conversion; S3.18 historical-deal input; S3.19 behavioral-data input; S3.20 intent-signal input; S3.21 qualification-data input; S3.22 Revenue Probability Score.

- **System 4:** S4.01 Customer Health Engine; S4.02 Product Adoption measure; S4.03 Feature Usage measure; S4.04 Engagement measure; S4.05 Satisfaction measure; S4.06 Churn Prediction Engine; S4.10 negative-sentiment detection for churn; S4.11 Churn Risk Score; S4.12 Expansion Engine; S4.15 renewal-opportunity detection; S4.16 Expansion Probability Score.

- **System 5:** S5.01 SDR Worker; S5.02 lead qualification; S5.03 lead nurturing; S5.05 meeting booking; S5.06 SDR voice; S5.07 SDR WhatsApp; S5.08 SDR email; S5.09 Sales Executive Worker; S5.10 product explanation; S5.12 proposal generation; S5.13 deal progression; S5.14 Customer Success Worker; S5.15 autonomous onboarding; S5.18 renewal preparation; S5.22 Support ticket resolution; S5.24 Collections Worker; S5.29 Account Manager Worker; S5.33 Executive Insights Worker; S5.34 leadership dashboards/recommendations.

- **System 6:** S6.02 action capture; S6.03 customer-response capture; S6.04 outcome capture; S6.05 performance measurement; S6.06 model update.

- **Communications:** C.01 Voice; C.02 Inbound Calls; C.03 Outbound Calls; C.07 WhatsApp voice notes; C.11 outbound email campaigns; C.13 personalized follow-ups; C.14 SMS; C.15 SMS reminders; C.16 SMS alerts; C.17 SMS notifications; C.19 chat lead capture; C.21 chat qualification.

- **AI models:** A.06 Speech-to-Text; A.07 Text-to-Speech; A.09 Emotion Detection; A.10 Lead Scoring; A.11 Conversion Prediction; A.13 Churn Prediction; A.17 Multi-Agent Orchestration; A.18 Planning.

- **Analytics:** AN.06 Customer Health; AN.09 Churn; AN.10 Response Time; AN.11 Resolution Time; AN.12 Agent Utilization; AN.13 Automation Rate.

- **Technology:** T.10 Claude; T.11 open-source models; T.12 PyTorch; T.13 XGBoost; T.15 Twilio.

## Immediate launch blockers, in order

1. Repair/backfill the required tenant's approved refund fact so operational policy body, PostgreSQL chunk approval and Qdrant approval agree; rerun its literal 45-day chat proof P17.
2. Mount and complete campaign endpoints/worker processing; declare provider settings in `Settings`; then prove real Brevo email, Twilio SMS, Meta WhatsApp, and voice calls with provider message/call IDs and delivery receipts.
3. Build the absent launch connectors (OneDrive, SharePoint, Notion, Confluence, LMS, accounting, ticketing) or explicitly remove them from launch scope.
4. Add a real ticketing-provider resolution loop for Support; current human escalation is durable, but ticket resolution is not.
5. Add backup/restore, security-review, monitoring-alert, failover and load/soak evidence before any status can become 4.

## Audit boundary

Repeated statements in the executive summary and problem statement are mapped to their canonical rows rather than double-counted. For example, “answering repetitive questions” maps to S5.21, “scheduling meetings” to S5.05, “sending reminders” to C.15/S5.25, and “continuously improves” to System 6. The separate hosted frontend was not source-audited because no frontend repository exists in this workspace. External OAuth/provider capabilities are never promoted above status 2 without a real provider run.
