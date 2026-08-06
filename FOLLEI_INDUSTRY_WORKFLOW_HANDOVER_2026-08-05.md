# Follei industry-workflow project handover

Prepared: 5 August 2026 (Asia/Kolkata)  
Repository: `follei-backend`  
Purpose: authoritative handover for the industry-pack workflow architecture, its current implementation, and the next delivery sequence.

## 1. Read this first

Follei is an AI-powered Autonomous Business Workforce Platform. Its operating model has three layers:

1. **Follei platform** — shared execution, storage, communications, verification, approvals, audit, tenancy, and security.
2. **Industry pack** — a Follei-owned, versioned node tree, domain schemas, knowledge categories, event vocabulary, deterministic rules, compliance gates, and default AI instructions for an industry.
3. **Company genome** — the tenant's own products, prices, policies, scripts, staff, approval limits, integrations, and operating preferences inside the selected industry's structure.

The immediate goal is to prove this architecture with Insurance. Healthcare, Education, Real Estate, and other packs must reuse the same platform rather than copy its runtime.

The governing rule is:

> AI can understand, classify, extract, converse, summarize, draft, and propose. Code validates, persists, routes, enforces policy, and performs external actions. Humans own regulated, financial, consequential, or final business decisions.

## 2. Final clarification: AI handoff and manual conversion

The universal end of an autonomous AI process is **human handoff**, not autonomous completion of a consequential transaction.

For a Sales process:

```text
Lead arrives
  -> deterministic pre-screen
  -> AI contact, discovery, nurture, and proposal preparation
  -> AI detects credible buying intent or a condition requiring a person
  -> code validates the structured result
  -> code creates a human-required handoff case
  -> AI automation for that case stops
  -> human handles negotiation, approval, issuance, or closing
  -> human optionally converts the lead into a customer
  -> human may optionally enter or attach invoice data
```

Important invariants:

- AI may propose `human_handoff_required`; it must not directly perform the database transition or assign itself authority.
- Code validates the AI result against an allow-listed event schema and creates the queue/task/approval record.
- Reaching the handoff queue does **not** mean the lead is a customer.
- Only an authorized human can perform `convert_lead_to_customer`.
- Invoice information is optional supporting business data. It is not a universal conversion prerequisite.
- Customer conversion must work when no invoice is supplied.
- If invoice data is provided, code validates and links it to the resulting customer/case; AI may extract fields but may not confirm payment or authorize conversion.
- For non-Sales processes, the same platform handoff primitive is used, but the human outcome is process-specific. For example, a claims adjuster resolves a claim; that action is not a lead-to-customer conversion.

Recommended lead states:

```text
new
pre_screening
ready_for_contact
engaging
interested
human_handoff_pending
human_in_progress
converted | closed_lost | disqualified
```

`converted` is reachable only through a human-authorized conversion command. The command should transactionally create or link the `Customer`, update the lead, record the actor and timestamp, and optionally attach invoice metadata.

## 3. Product target

Industry selection is mandatory during onboarding. After basic account creation, the tenant selects an industry before uploading business data or creating/importing leads. Follei locks the tenant to a versioned industry pack, instantiates the pack's root node tree, and classifies all subsequent company knowledge using that pack's category schema.

The Insurance lifetime tree is:

```text
Eligibility Check
  -> Sales
       -> human handoff
       -> human closes or declines
       -> optional manual lead-to-customer conversion
  -> after conversion, when applicable:
       -> Payment & Renewal Tracking
       -> Claims
            -> after claim resolution: Reapply / Upgrade
```

The first production slice should remain narrower:

```text
mandatory Insurance selection
  -> categorized company knowledge
  -> eligibility/pre-screen
  -> first contact
  -> discovery and plan nurture
  -> quote/application preparation
  -> validated human handoff
  -> optional human conversion to customer
  -> complete case audit
```

Payment/renewal, claims, and reapply/upgrade are the next Insurance phases. They should not delay proof of the first slice.

## 4. Core vocabulary

| Term | Meaning |
|---|---|
| Tenant | One customer organization using Follei. |
| Industry pack | Follei-owned, versioned domain package for one industry. |
| Company genome | Tenant-specific facts and configuration inside the pack's schemas. |
| Workflow template | Immutable, versioned node graph published by Follei. |
| Workflow instance | A tenant's materialized template version plus a safe override layer. |
| Parent node | A business capability that starts and owns a child workflow. |
| Child workflow | A complete graph executed beneath a parent node. |
| Action primitive | Atomic operation such as email, call, wait, retrieve, validate, task, approval, or CRM update. |
| Node contract | Purpose, inputs, execution, decision, output, verification, escalation, and audit. |
| Handoff package | Structured context, evidence, citations, conversation summary, missing items, recommended next action, and ownership metadata given to a human. |
| Conversion command | Human-authorized transaction that turns a lead into or links it to a customer. |

## 5. What exists in the repository now

### 5.1 Strong existing platform foundations

- Multi-tenant PostgreSQL models and APIs.
- Business document and website ingestion.
- Structured extraction and human fact review.
- PostgreSQL canonical state, FerretDB flexible memory, and Qdrant semantic evidence.
- Lead import, normalization, deduplication, enrichment, scoring evidence, and lead memory.
- Grounded retrieval with citations.
- Email outbox and provider integration code.
- Conversation, message, and call-related models.
- Versioned flat workflow definitions and durable enrollments.

### 5.2 Industry-workflow foundation implemented in the current working tree

The current uncommitted implementation adds:

- `WorkflowTemplate`: Follei-owned versioned graph and node contracts.
- `TenantWorkflowInstance`: tenant materialization with parent/child relationships and overrides.
- `WorkflowApproval`: canonical human approval/task/SLA record.
- Parent/child flow enrollments.
- Structured node output, decision, verification, and audit metadata.
- Validation that every node has all eight node-contract elements.
- Safe tenant override validation and draft activation.
- Deterministic Insurance pre-screen outcomes.
- Structured first-contact and discovery event schemas.
- Document readiness checks.
- Human handoff and approval gates.
- Recursive case audit retrieval.
- Registration/onboarding hooks that instantiate the current runtime.

Primary files:

| File | Current responsibility |
|---|---|
| `app/models/flows.py` | Canonical template, instance, enrollment, execution, approval, and communication-asset models. |
| `app/services/flows/service.py` | Template definitions, materialization, validation, execution, subflows, Insurance decisions, and approvals. |
| `app/routers/flows.py` | Template, instance, override, event, document, approval, and audit APIs. |
| `app/routers/api_v1.py` | Main registration path and current default runtime creation. |
| `app/routers/onboarding.py` | Company profile and optional industry selection. |
| `app/routers/tenant.py` | Alternate tenant creation path. |
| `app/services/organization_service.py` | Organization creation and workflow initialization. |
| `app/services/knowledge/memory_store.py` | Flexible workflow/lead memory projection. |
| `alembic/versions/20260804_industry_workflow_runtime.py` | Additive workflow-runtime migration. |
| `tests/flows/test_workflow_templates.py` | Template, contract, and override tests. |

### 5.3 Verification already performed

- Six focused workflow tests passed.
- SQLAlchemy mapper configuration passed.
- Python compilation passed.
- `git diff --check` passed.
- The new migration is the Alembic head.
- Migration-specific offline PostgreSQL SQL generation passed.

The migration has not been applied to a real shared database in this work. No live-provider end-to-end Insurance case has been certified.

## 6. Current implementation versus the target

| Capability | Current status | Required target change |
|---|---|---|
| Industry selection | Optional and separate from account registration | Mandatory step 2; blocks ingestion and lead creation |
| Industry-pack association | Tenant has nullable text `industry` | Canonical pack ID and locked pack version |
| Default root | Universal seven-slot template | Active industry pack's real root tree |
| Insurance slice | Eligibility, engagement, preparation, handoff templates exist | Recompose beneath Eligibility and Sales parent nodes |
| AI contact/discovery | Structured events are accepted | Connect real conversation output to event submission |
| Handoff | Approval/task/SLA records exist | Add explicit universal handoff package and terminal AI boundary |
| Human conversion | Customer model exists | Add authorized conversion command and complete audit |
| Invoice | Generic invoice model exists | Make optional on conversion; distinguish business invoice from Follei subscription billing |
| Post-sale subject | Enrollment requires a lead | Support lead, customer, policy, claim, or generic case subjects |
| Renewals | Generic payment records exist | Insurance policy/payment schedule and recurring workflow |
| Claims | Some extraction code exists, no complete claim domain | Claim model, events, document state, adjuster gate |
| Upgrade | Not implemented | Triggered child workflow after eligible event |
| Parallel long-lived flows | Runtime primarily advances one current path | Independent recurring/event-triggered customer workflows |
| UI | Old flat builder | Parent/child tree, handoff queue, conversion form, audit view |

## 7. Shared code for every industry

The following must remain industry-independent:

### Identity and governance

- Tenant isolation and authentication
- User roles and permissions
- Pack/version activation mechanics
- Onboarding completion enforcement
- Human authorization checks

### Workflow runtime

- Template publishing and immutability
- Tenant instance materialization
- Parent/child execution
- Event validation
- Waiting, retry, timeout, and idempotency behavior
- Structured output validation
- Execution verification
- Audit logging
- Overrides and activation
- Recurring/event-triggered scheduling

### Shared action primitives

- `send_email`
- `place_call`
- `wait`
- `retrieve_approved_knowledge`
- `validate_data`
- `collect_document`
- `create_task`
- `request_human_handoff`
- `request_approval`
- `update_crm`
- `receive_event`
- `start_subflow`
- `complete`
- `stop`

### Communications and integrations

- Provider adapter interfaces
- Durable outbox
- Provider receipt handling
- Retries and idempotency
- OAuth lifecycle
- CRM mapping infrastructure
- Delivery and side-effect verification

### Knowledge and AI controls

- Ingestion pipeline
- Approved-source retrieval
- Citation capture
- Model/prompt version logging
- Structured-output schemas
- Safety and policy validation

### Universal human boundary

Every industry can use `request_human_handoff`. It must:

1. Accept a validated reason and structured handoff package.
2. Create a canonical queue/task record.
3. Assign an owner using tenant rules.
4. Start an SLA.
5. Notify the human through configured channels.
6. Stop or pause AI execution for the consequential case.
7. Record the eventual human outcome.

## 8. What changes by industry

An industry pack defines:

- Root business node tree
- Child workflow templates
- Domain schemas
- Knowledge/document categories
- Required company facts
- Allowed business events and outcomes
- Deterministic routing policies
- Required-document checklists
- Protected human gates
- Compliance language and prohibited AI behavior
- Default discovery question sets
- Default prompts and communication policies
- Verification requirements
- Escalation roles and SLA defaults

Examples:

| Area | Insurance | Healthcare | Education |
|---|---|---|---|
| Intake | Lead and consent pre-screen | Patient/service intake | Student/course inquiry |
| AI work | Product discovery and nurture | Service navigation and scheduling support | Course discovery and application guidance |
| Consequential handoff | Agent/underwriter | Qualified staff/clinician | Admissions/finance staff |
| Human final action | Close/issue/convert | Clinical or administrative decision | Admission/enrollment decision |
| Domain records | Policy, premium, claim, renewal | Patient request, appointment, referral | Application, enrollment, course |

Do not implement this as scattered `if industry == ...` logic. The engine loads the active pack's definitions and invokes shared primitives.

## 9. What changes by tenant

The company genome supplies:

- Products and plans
- Carrier/provider/partner relationships
- Prices and permitted offers
- Company-specific eligibility constraints
- Approved scripts and content
- Business hours and supported channels
- Human queues, ownership, and approval limits
- CRM field mappings
- Required tenant documents
- Tenant thresholds that the industry pack explicitly allows overriding
- Communication tone and question ordering

Tenant overrides cannot remove mandatory compliance controls, weaken protected human gates, or activate an unvalidated workflow.

## 10. Static code, configuration, AI, and human ownership

### Static platform code

Keep these deterministic and code-owned:

- Tenant authorization
- Schema validation
- State transition engine
- Idempotency and retries
- Database transactions
- Provider invocation
- Approval enforcement
- Audit logging
- Pack compatibility validation
- Conversion authorization
- Prohibition on AI-driven customer conversion

### Versioned industry configuration

Move these out of a single large Python service and into canonical pack definitions:

- Node trees and edges
- Node contracts
- Event vocabularies
- Domain schemas
- Knowledge categories
- Required document lists
- Default prompts
- Protected nodes and approval policies
- Default escalation roles and SLAs

Published pack versions are canonical PostgreSQL records. Repository manifests may seed them, but AI must not silently rewrite a published pack.

### AI-defined at runtime

AI may:

- Propose a document category
- Extract structured company facts
- Ask adaptive discovery questions
- Summarize needs and objections
- Draft approved explanations, emails, and proposals
- Detect interest or request for a human
- Propose a handoff reason
- Assemble a handoff summary with evidence and citations
- Extract optional invoice fields

All AI outputs must be schema-valid, source-aware where factual, and treated as proposals.

### Human-owned

Humans own:

- Approval of consequential company facts and overrides
- Final eligibility/underwriting or equivalent regulated decisions
- Binding, issuance, negotiation, exceptions, and regulated advice
- Claim settlement
- Lead-to-customer conversion
- Optional invoice entry/attachment
- Final resolution of a human handoff case

## 11. Recommended architecture refactor

The current proof places template definitions and much Insurance logic in `app/services/flows/service.py`. Preserve its behavior while separating concerns:

```text
app/
  workflows/
    runtime/
      executor.py
      transitions.py
      subflows.py
      scheduling.py
      verification.py
    contracts/
      node_contract.py
      event_contract.py
      handoff_contract.py
    primitives/
      communications.py
      knowledge.py
      documents.py
      tasks.py
      approvals.py
      crm.py
    services/
      templates.py
      instances.py
      audit.py
      conversion.py
  industry_packs/
    registry.py
    insurance/
      manifest.py or manifest.yaml
      node_tree.py or node_tree.yaml
      categories.py or categories.yaml
      schemas.py
      policies.py
      prompts.py
      verification.py
```

The format can be chosen during implementation. The architectural requirement is separation between shared runtime and pack-owned definitions, not YAML specifically.

## 12. Required data-model changes

### Industry governance

- `industry_packs`
- `industry_pack_versions`
- tenant `active_industry_pack_version_id`
- onboarding status and industry selection audit

### Generalized workflow subject

Current enrollments require `lead_id`. Long-lived industry workflows need either:

- explicit nullable `lead_id`, `customer_id`, `policy_id`, and `claim_id`, with a constraint allowing the appropriate combination; or
- a carefully designed `subject_type` and `subject_id` plus canonical relationship tables.

Choose this before implementing renewals or claims. The first option provides stronger relational integrity; the second is more flexible but easier to misuse.

### Human handoff

Add or formalize:

- handoff reason
- handoff type
- structured summary
- evidence and citation references
- AI recommendation, clearly labeled non-authoritative
- assigned queue/user
- SLA
- state: pending, accepted, in progress, resolved, rejected
- human outcome and notes

The existing `WorkflowApproval` and `AgentTask` can be extended or wrapped rather than duplicated.

### Manual conversion

Add a canonical conversion record with:

- tenant
- lead
- customer
- originating enrollment/case
- converted by
- converted at
- conversion reason/outcome
- optional invoice ID or optional invoice payload reference
- optional policy/external CRM reference
- idempotency key
- audit metadata

Conversion must be transactional and tenant-scoped.

### Insurance post-sale

Before post-sale implementation, define explicit customer-policy, payment schedule, renewal, claim, and upgrade records. Do not confuse the existing knowledge `Policy` record with an issued insurance policy.

## 13. API behavior to add

### Onboarding

- Select and lock industry pack
- Retrieve pack requirements/categories
- Check onboarding readiness
- Block ingestion/lead creation until ready
- Controlled administrator migration for an incorrect industry selection

### Handoff

- List human-required cases
- Accept/assign handoff
- Record human outcome
- Request more information
- Resolve/close handoff

### Conversion

- Convert lead to customer, human authorization required
- Accept optional invoice data/document
- Link optional policy or CRM references
- Return the complete conversion audit

### Industry events

- Submit allow-listed structured events
- Verify provider/system events
- Start pack-defined event workflows
- Preserve idempotency and provenance

## 14. Delivery sequence

### P0 — preserve and verify the current work

1. Review the current staged working tree before editing.
2. Apply the additive migration only to an isolated test database first.
3. Run workflow, tenant-isolation, migration, and regression tests.
4. Preserve the existing flat flow for migration compatibility until active tenants are handled.

### P1 — correct the universal boundary

1. Formalize `human_handoff_required` as the terminal autonomous outcome.
2. Create a complete handoff package.
3. Ensure code, not model output, creates the task/queue transition.
4. Add human case acceptance and outcome APIs.
5. Add the authorized manual conversion command with optional invoice input.

Acceptance: AI can bring an interested lead to a human with complete evidence, cannot convert it, and a human can convert with or without invoice data.

### P2 — mandatory industry onboarding

1. Add canonical industry pack/version records.
2. Make industry selection mandatory.
3. Block document and lead ingestion before selection.
4. Instantiate the selected industry's root.
5. Categorize the first document batch against the pack taxonomy.

Acceptance: no active tenant enters the product with an uncategorized industry state.

### P3 — Insurance first slice end to end

1. Recompose current Insurance templates beneath Eligibility and Sales.
2. Wire email/provider receipts into first-contact outcomes.
3. Wire the AI conversation output into structured discovery and handoff events.
4. Complete one tenant-scoped CRM connector.
5. Build handoff, conversion, nested workflow, and audit UI.
6. Run a seeded end-to-end case with failure and retry scenarios.

Acceptance: Insurance tenant -> categorized knowledge -> lead -> pre-screen -> engagement -> human handoff -> optional manual conversion -> auditable completion.

### P4 — Insurance post-sale

1. Customer insurance policy domain.
2. Payment and renewal event model.
3. Recurring renewal workflow and retention handoff.
4. Claims intake, document tracking, adjuster gate, and resolution.
5. Reapply/upgrade child workflow.

Do not begin P4 until P3 is proven with real provider receipts and a real human handoff.

## 15. Progress estimate

| Scope | Estimated completion |
|---|---:|
| Shared workflow-engine foundation | 70–75% |
| Eligibility and Sales backend structure | 60–65% |
| Real AI-to-handoff integration | 35–40% |
| Manual human conversion with optional invoice | 10–15% |
| Mandatory industry onboarding | 20–25% |
| Insurance post-sale lifetime tree | 5–10% |
| Entire Insurance v2 demonstrable product | 30–35% |
| Production readiness of this industry slice | 25–30% |

These are engineering estimates, not measured release metrics. The current foundation is meaningful, but live channel verification, UI, database-backed integration tests, one complete CRM connection, operational retries, and security proof remain.

## 16. Known risks and decisions

1. **The supplied Insurance Node Tree v2 attachment is truncated** during the Reapply/Upgrade diagram. Obtain the complete source before finalizing that child workflow.
2. Decide whether one tenant can ever operate multiple industries. The current direction assumes one active primary pack with controlled migration.
3. Decide whether human handoff and approval are one model or related models. Avoid duplicate sources of truth.
4. Decide the generalized workflow-subject model before claims and renewals.
5. Define what “policy issued” means and which human/external-system evidence is authoritative.
6. Clarify whether generic `Invoice` represents tenant business invoices, Follei subscription billing, or both. Do not mix them silently.
7. Voice, email receipt handling, CRM writes, and external notification delivery are not production-certified.
8. Tenant-pack configuration must not permit removal of protected human gates.

## 17. Instructions for the next coding agent

```text
Read FOLLEI_INDUSTRY_WORKFLOW_HANDOVER_2026-08-05.md completely before editing.
The authoritative boundary is: AI may detect buying intent and propose a
human handoff; validated code creates the handoff; only a human can convert a
lead to a customer; invoice data is optional.

Inspect git status before changes because the industry workflow implementation
and migration are currently staged working-tree changes. Preserve unrelated
work. Verify the migration on an isolated database and run focused tests first.

Implement in this order unless explicitly reprioritized:
1. universal structured human handoff and manual conversion command;
2. mandatory industry-pack onboarding and ingestion gate;
3. Insurance Eligibility + Sales end-to-end integration;
4. UI, one CRM, provider receipts, retries, and audit acceptance;
5. renewals, claims, and upgrade only after the first slice passes.

Do not let an LLM write customer status, create a customer, approve a regulated
decision, or perform a consequential external action directly. Model output is
a proposal. Validate it with code, record evidence, and require the configured
human decision.
```

## 18. Definition of success

Follei's industry architecture succeeds when a new tenant can select an industry, upload only company-specific information, receive a working industry-native node tree, and safely customize allowed parts without rebuilding the platform. AI performs the conversational and interpretive work, deterministic code controls execution, and humans take over at consequential boundaries.

For the Insurance first slice, success is not “AI sold a policy.” Success is:

> Follei understood the company, safely qualified and nurtured the lead, recognized credible interest, produced an evidence-backed human handoff, stopped autonomous action, allowed an authorized person to decide the outcome, optionally converted the lead into a customer with or without invoice information, and preserved the entire history as one auditable case.
