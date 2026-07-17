"""Lead Import service — orchestrates parsing, AI extraction, validation, dedup, preview, and commit."""

import json
import logging
import re
import time
from uuid import UUID

from app.domains.lead_import.exceptions import JobNotFoundError, JobNotReadyError
from app.domains.lead_import.constants import ImportStatus, RowStatus
from app.domains.lead_import.models import LeadImportJob, LeadImportRow
from app.domains.lead_import.repository import LeadImportRepository
from app.domains.lead_import.parsers import ParserFactory, ExtractedDocument
from app.domains.lead_import.validators import validate_lead_row, is_blank_row
from app.domains.lead_import.utils import (
    split_full_name,
    normalize_email,
    normalize_phone,
    normalize_website,
    calculate_confidence,
)
from app.domains.lead_import.scoring import (
    calculate_quality_score,
    compute_quality_statistics,
)
from app.domains.lead_import.intelligence import compute_lead_intelligence

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are an intelligent data extraction engine for a CRM system. Your job is to analyze uploaded documents and extract lead/contact/business information.

## Document Understanding
First, determine what kind of document this is. Possible types include:
- employee_directory, business_directory, crm_export, sales_leads, customer_list
- invoice, event_registration, conference_attendees, vendor_list, marketing_list
- purchase_records, company_report, government_data, phone_book, import_list
- resume, tender, unknown

If the document does NOT contain contact/lead records (e.g., it is a legal notice, advertisement, paragraph text, image without data, table of contents), return {"document_type": "unknown", "document_confidence": 0, "document_reason": "No contact records detected", "leads": []}.

## Extraction Rules
1. Extract ONLY rows that represent people, contacts, prospects, or companies that could become leads.
2. IGNORE completely: headers, footers, page numbers, logos, navigation, pricing columns, totals, subtotals, GST, tax lines, paragraphs, signatures, advertisements, terms of service, legal notices, table of contents, page separators ("--- Page 1 ---"), sheet labels.
3. Pay attention to ALL possible column names. The document might use different headers. Here are common variants:
   - Name fields: "Name", "Contact Name", "Employee", "Owner", "Representative", "Sales Person", "Manager", "Primary Contact", "Stakeholder", "Full Name", "First Name", "Last Name", "Fname", "Lname", "Given Name", "Surname", "Forename", "Christian Name", "Person Name"
   - Company: "Company", "Organization", "Organisation", "Business", "Firm", "Account", "Employer", "Company Name", "Business Name", "Org", "Works At"
   - Email: "Email", "E-mail", "Mail", "Email Address", "Contact Email", "Email ID", "Mail ID", "Email Addresses"
   - Phone: "Phone", "Mobile", "Cell", "Telephone", "Tel", "Contact No", "Phone Number", "Mobile Number", "Phone No", "Mobile No", "Contact", "Phone #"
   - Website: "Website", "Web", "URL", "Site", "Domain", "Web Page", "Web Site"
   - Social: "LinkedIn", "LinkedIn URL", "LinkedIn Profile", "Linkedin"
   - Title: "Designation", "Title", "Position", "Role", "Job Title", "Job Role", "Job Position"
   - Department: "Department", "Dept", "Division", "Unit", "Team", "Business Unit"
   - Location: "City", "Town", "State", "Province", "Country", "Region", "Location", "Zip", "Postal Code", "Pincode", "Zip Code", "Territory"
   - Industry: "Industry", "Sector", "Vertical", "Business Type", "Category"
   - Notes: "Notes", "Comments", "Remarks", "Description", "Additional Info", "Note"
4. If a field is not found or unclear, set it to null. Do not guess.

## Output Fields (for each lead)
- first_name, last_name: split full names intelligently. "John David Smith" -> first_name="John", last_name="David Smith" if middle name, otherwise first_name="John", last_name="Smith". If unsure, set first_name to the full name and last_name to null.
- company, designation, department
- email, phone, website, linkedin
- city, state, country, postal_code
- industry
- notes
- confidence (0.0 to 1.0): based on completeness and clarity of the record
- confidence_reason (string): brief explanation of the confidence score
- source_page (int or null): the page/sheet number where this row was found (1-based)
- source_row (int or null): the row number within the source page (1-based)
- document_section (string or null): section of the document (e.g., "table_1", "text_block_2")
- duplicate_probability (int 0-100): AI estimate of likelihood this record already exists in a CRM (based on name + company overlap + commonality)

## Normalization
- Normalize emails to lowercase
- Normalize phone numbers to +<digits> format (e.g., +919876543210)
- Normalize websites to include https:// prefix

## Output Format
Return a JSON object with two keys:
{
  "document_type": "<inferred document type>",
  "document_confidence": 0.0-1.0,
  "document_reason": "<brief explanation of classification>",
  "leads": [
    {
      "first_name": "...",
      "last_name": "...",
      "company": "...",
      "designation": "...",
      "department": null,
      "email": "...",
      "phone": "...",
      "website": "...",
      "linkedin": "...",
      "city": "...",
      "state": "...",
      "country": "...",
      "postal_code": null,
      "industry": "...",
      "notes": "...",
      "confidence": 0.98,
      "confidence_reason": "Complete record with name, email, phone, and company",
      "source_page": 1,
      "source_row": 3,
      "document_section": "table_1",
      "duplicate_probability": 15
    }
  ]
}

If no leads are found, return {"document_type": "unknown", "document_confidence": 0, "document_reason": "No contact records detected in this document", "leads": []}.
Respond with ONLY valid JSON. No explanation, no markdown formatting."""


EXTRACTION_USER_PROMPT_TEMPLATE = """Extract lead/contact records from the following document content:

{content}

Remember: return ONLY a JSON object with document_type and leads array. If the document contains tables, pay special attention to rows that contain contact information."""


ENRICHMENT_SYSTEM_PROMPT = """You are a data enrichment assistant for a CRM system. Your task is to fill in missing fields for lead records using available context clues.

## Context You Can Use
- Email domain → company name and website (e.g., john@acme.com → "Acme", https://acme.com)
- Person name patterns → proper name formatting
- Company name → industry, company size range, likely HQ country
- Job title/designation → department
- Phone country code → country
- Website domain → company name, industry
- Designation → seniority level, department

## Rules
1. Only fill fields that are null/missing. NEVER change existing values.
2. Only make high-confidence inferences. Leave as null if unsure.
3. Do not modify email, phone, or confidence fields.
4. Add a log entry for each inference explaining the source.

## Output Fields (per lead, in addition to existing fields)
- enrichment (dict): contains:
  - inferred_company: str | null — company name inferred from email domain
  - inferred_industry: str | null — industry inferred from company name or website
  - inferred_country: str | null — country inferred from phone code or domain TLD
  - inferred_company_size: str | null — size range (e.g., "1-10", "11-50", "51-200", "201-1000", "1000+")
  - inferred_website: str | null — website inferred from email domain
  - inferred_designation: str | null — role inferred from name + company context
  - log: list[str] — human-readable explanations of each inference

## Output Format
Return a JSON object with a single key "leads" containing the enriched lead records as an array. Preserve all original fields exactly and add the enrichment object to each.

If enrichment fails or finds nothing to add, return the original leads unchanged.

Respond with ONLY valid JSON. No explanation, no markdown formatting."""


ENRICHMENT_USER_PROMPT_TEMPLATE = """Enrich the following lead records by filling in missing fields based on available context:

{lead_data}

Return ONLY a JSON object with key "leads" containing the enriched lead array. Preserve all original fields. Add an "enrichment" object with inferred fields and a log."""


LEAD_FIELD_MAP = {
    "first_name": "first_name",
    "last_name": "last_name",
    "company": "company",
    "designation": "designation",
    "department": "department",
    "email": "email",
    "phone": "phone",
    "website": "website",
    "linkedin": "linkedin",
    "city": "city",
    "state": "state",
    "country": "country",
    "postal_code": "postal_code",
    "industry": "industry",
    "notes": "notes",
    "confidence": "confidence",
    "confidence_reason": "confidence_reason",
    "source_page": "source_page",
    "source_row": "source_row",
    "document_section": "document_section",
    "duplicate_probability": "duplicate_probability",
}

# Column name variants for heuristic extraction (maps variant -> canonical field)
HEURISTIC_COLUMN_MAP: dict[str, list[str]] = {}
for canonical, variants in [
    ("full_name", ["name", "full name", "fullname", "contact name", "contact_name", "employee", "employee name", "employee_name", "representative", "person name", "person_name", "stakeholder", "primary contact", "primary_contact", "owner"]),
    ("first_name", ["first name", "firstname", "fname", "given name", "given_name", "forename"]),
    ("last_name", ["last name", "lastname", "lname", "surname", "family name", "family_name"]),
    ("company", ["company", "organization", "organisation", "org", "business", "firm", "account", "employer", "company name", "company_name", "business name", "business_name", "works at", "works_at"]),
    ("email", ["email", "e-mail", "mail", "email address", "email_address", "contact email", "contact_email", "email id", "email_id", "mail id", "mail_id"]),
    ("phone", ["phone", "mobile", "cell", "telephone", "tel", "contact no", "contact_no", "contact number", "contact_number", "phone number", "phone_number", "mobile number", "mobile_number", "phone no", "phone_no", "mobile no", "mobile_no", "phone #"]),
    ("website", ["website", "web", "url", "site", "domain", "web page", "web_page", "web site", "web_site"]),
    ("linkedin", ["linkedin", "linked in", "linked_in", "linkedin url", "linkedin_url", "linkedin profile", "linkedin_profile"]),
    ("designation", ["designation", "title", "position", "role", "job title", "job_title", "job role", "job_role", "job position", "job_position"]),
    ("department", ["department", "dept", "division", "unit", "team", "business unit", "business_unit"]),
    ("city", ["city", "town", "locality", "location city", "location_city"]),
    ("state", ["state", "province", "region", "territory"]),
    ("country", ["country", "nation", "nationality", "region country", "region_country"]),
    ("postal_code", ["postal code", "postal_code", "zip", "zip code", "zip_code", "pincode", "pin code", "pin_code", "postcode"]),
    ("industry", ["industry", "sector", "vertical", "business type", "business_type", "category"]),
    ("notes", ["notes", "comments", "remarks", "description", "additional info", "additional_info", "note"]),
]:
    HEURISTIC_COLUMN_MAP[canonical] = variants


# Email typo corrections for common domain misspellings
EMAIL_TYPO_MAP: dict[str, str] = {
    "gnail.com": "gmail.com",
    "gmial.com": "gmail.com",
    "gmil.com": "gmail.com",
    "gmaill.com": "gmail.com",
    "gmail.co": "gmail.com",
    "g-mail.com": "gmail.com",
    "yahooo.com": "yahoo.com",
    "yahhoo.com": "yahoo.com",
    "yaho.com": "yahoo.com",
    "hotmai.com": "hotmail.com",
    "hotmial.com": "hotmail.com",
    "hotmail.co": "hotmail.com",
    "outloo.com": "outlook.com",
    "outlok.com": "outlook.com",
    "outllook.com": "outlook.com",
    "aol.co": "aol.com",
    "aol.cm": "aol.com",
}

# Name formatting corrections
NAME_TYPO_MAP: dict[str, str] = {
    "dr.": "",
    "dr ": "",
    "mr.": "",
    "mr ": "",
    "mrs.": "",
    "mrs ": "",
    "ms.": "",
    "ms ": "",
    "prof.": "",
    "prof ": "",
    "sir": "",
}


def _apply_batch_corrections(rows: list) -> list:
    """Apply batch corrections (typos, formatting) to a list of extracted lead dicts.

    Never overwrites rows where the user_edited flag is set.
    """
    corrected = []
    for lead in rows:
        if lead.get("user_edited"):
            corrected.append(lead)
            continue
        lead = _correct_email_typo(lead)
        lead = _correct_name_typo(lead)
        lead = _correct_phone_format(lead)
        corrected.append(lead)
    return corrected


def _correct_email_typo(lead: dict) -> dict:
    email = (lead.get("email") or "").strip()
    if not email or "@" not in email:
        return lead
    local, domain = email.rsplit("@", 1)
    fixed = EMAIL_TYPO_MAP.get(domain.lower())
    if fixed:
        lead["email"] = f"{local}@{fixed}"
        lead.setdefault("corrections", []).append(f"email domain typo: {domain} -> {fixed}")
    return lead


def _correct_name_typo(lead: dict) -> dict:
    for field in ("first_name", "last_name"):
        val = (lead.get(field) or "").strip()
        if not val:
            continue
        original = val
        for prefix, replacement in NAME_TYPO_MAP.items():
            if val.lower().startswith(prefix):
                val = val[len(prefix):].strip()
        if val != original:
            lead[field] = val
            lead.setdefault("corrections", []).append(f"{field}: removed prefix '{original[:4]}' -> '{val}'")
    return lead


def _correct_phone_format(lead: dict) -> dict:
    phone = lead.get("phone")
    if not phone or not isinstance(phone, str):
        return lead
    cleaned = re.sub(r"[^\d+]", "", phone)
    if not cleaned.startswith("+"):
        cleaned = "+" + re.sub(r"[^\d]", "", cleaned)
    if cleaned != phone:
        lead["phone"] = cleaned
        lead.setdefault("corrections", []).append(f"phone reformatted: '{phone}' -> '{cleaned}'")
    return lead


class LeadImportService:
    """High-level service orchestrating the lead import pipeline."""

    STAGE_NAMES = {
        0: "parsing",
        1: "extracting",
        2: "enriching",
        3: "intelligence",
        4: "correcting",
        5: "validating",
        6: "deduplicating",
        7: "reviewing",
        8: "finalizing",
    }

    def __init__(self, repo: LeadImportRepository):
        self.repo = repo

    async def process_upload(
        self,
        tenant_id: UUID,
        filename: str,
        file_type: str,
        file_path: str,
        uploaded_by: str | None = None,
        progress_callback: callable = None,
    ) -> LeadImportJob:
        """Full upload -> parse -> extract -> enrich -> intelligence -> correct -> validate -> dedup -> review -> ready."""
        timings: dict[str, float] = {}
        job = self.repo.create_job(
            tenant_id=tenant_id,
            filename=filename,
            file_type=file_type,
            uploaded_by=uploaded_by,
        )
        self.repo.db.flush()

        try:
            # Phase 2: Parse
            t0 = time.perf_counter()
            self.repo.update_job_status(job.id, ImportStatus.PARSING)
            parser = ParserFactory.get_parser(file_type)
            doc = await parser.parse(file_path)
            timings["parse"] = time.perf_counter() - t0
            if progress_callback:
                progress_callback(0, 1.0)

            # Phase 3: AI Extraction with document classification
            t0 = time.perf_counter()
            self.repo.update_job_status(job.id, ImportStatus.EXTRACTING)
            leads, doc_classification = await self._extract_leads(doc, job.id)
            timings["extract"] = time.perf_counter() - t0

            # Store document classification in job statistics
            if doc_classification and doc_classification.get("type"):
                self._store_doc_classification(job.id, doc_classification)
            if progress_callback:
                progress_callback(1, 1.0)

            logger.debug("After extraction: %d leads, doc_classification=%s", len(leads), doc_classification)

            # Phase 3b: Enrich leads
            t0 = time.perf_counter()
            self.repo.update_job_status(job.id, ImportStatus.ENRICHING)
            leads = await self._enrich_leads(leads)
            timings["enrich"] = time.perf_counter() - t0
            if progress_callback:
                progress_callback(2, 1.0)

            # Phase 3c: Lead Intelligence
            t0 = time.perf_counter()
            self.repo.update_job_status(job.id, ImportStatus.INTELLIGENCE)
            for lead in leads:
                lead["intelligence"] = compute_lead_intelligence(lead)
            timings["intelligence"] = time.perf_counter() - t0
            if progress_callback:
                progress_callback(3, 1.0)

            # Phase 3d: Batch Corrections
            t0 = time.perf_counter()
            self.repo.update_job_status(job.id, ImportStatus.CORRECTING)
            leads = _apply_batch_corrections(leads)
            timings["corrections"] = time.perf_counter() - t0
            if progress_callback:
                progress_callback(4, 1.0)

            # Phase 3e: Quality scoring
            for lead in leads:
                lead["quality"] = calculate_quality_score(lead)

            # Store quality aggregates in job statistics
            quality_stats = compute_quality_statistics(leads)
            job_stats = dict(job.statistics or {})
            job_stats["quality"] = quality_stats
            job.statistics = job_stats
            self.repo.db.flush()

            # Store extracted data as rows (with spam/review flags from intelligence)
            rows_to_insert = []
            for i, lead in enumerate(leads):
                intelligence = lead.get("intelligence", {})
                spam_score = intelligence.get("spam_score", 0)
                trust_score = intelligence.get("trust_score", 100)
                completeness = intelligence.get("contact_completeness", 100)
                is_spam = spam_score > 50
                needs_review = trust_score < 50 or completeness < 30
                row_status = RowStatus.SPAM if is_spam else (RowStatus.NEEDS_REVIEW if needs_review else RowStatus.PENDING)
                rows_to_insert.append({
                    "job_id": job.id,
                    "tenant_id": tenant_id,
                    "row_index": i,
                    "raw_data": {},
                    "extracted_data": lead,
                    "confidence": lead.get("confidence", calculate_confidence(lead)),
                    "status": row_status,
                    "selected": not is_spam,
                })

            if rows_to_insert:
                self.repo.bulk_create_rows(rows_to_insert)

            # Phase 4: AI Review — promote high-trust needs_review rows before validate/dedup
            t0 = time.perf_counter()
            self.repo.update_job_status(job.id, ImportStatus.REVIEWING)
            self._flag_review_rows(job.id)
            timings["review"] = time.perf_counter() - t0
            if progress_callback:
                progress_callback(5, 1.0)

            # Phase 5: Validate
            t0 = time.perf_counter()
            self.repo.update_job_status(job.id, ImportStatus.VALIDATING)
            self._validate_rows(job.id)
            timings["validate"] = time.perf_counter() - t0
            if progress_callback:
                progress_callback(6, 1.0)

            # Phase 6: Deduplicate
            t0 = time.perf_counter()
            self._deduplicate_rows(job.id)
            timings["dedup"] = time.perf_counter() - t0
            if progress_callback:
                progress_callback(7, 1.0)

            # Phase 7: Finalize
            self.repo.update_job_statistics(job.id)
            self.repo.update_job_status(job.id, ImportStatus.PREVIEW_READY, completed_at=None)

            # Store timings in job statistics
            job_stats = dict(job.statistics or {})
            job_stats["metrics"] = {"timings_seconds": timings, "total_seconds": sum(timings.values())}
            job.statistics = job_stats
            self.repo.db.flush()
            if progress_callback:
                progress_callback(8, 1.0)

        except Exception as e:
            logger.exception("Lead import processing failed for job %s", job.id)
            self.repo.update_job_status(
                job.id, ImportStatus.FAILED,
                error_message=str(e)[:2000],
                completed_at=None,
            )

        return job

    async def _extract_leads(
        self, doc: ExtractedDocument, job_id: UUID | None = None
    ) -> tuple[list[dict], dict | None]:
        """Send document content to LLM and parse extracted lead records.

        Returns (leads, doc_classification_or_None).
        """
        content = doc.text

        # Include table data as structured text
        if doc.tables:
            table_sections = []
            for ti, table in enumerate(doc.tables):
                rows_text = "\n".join(" | ".join(cell for cell in row) for row in table)
                table_sections.append(f"[Table {ti + 1}]\n{rows_text}")
            content += "\n\n" + "\n\n".join(table_sections)

        # Truncate if too large (local LLM context limits ~2048-4096 tokens)
        max_chars = 4000
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[...content truncated due to length...]"

        # Try local LLM extraction
        leads, doc_classification = await self._call_llm(content)

        if not leads:
            # Fallback: try heuristic extraction
            logger.debug("LLM returned 0 leads, falling back to heuristic")
            leads = self._heuristic_extract(doc)
            doc_classification = None

        # Post-process: normalize and enrich each lead
        for lead in leads:
            self._normalize_lead(lead)

        logger.debug("Extraction produced %d leads", len(leads))
        return leads, doc_classification

    async def _call_llm(self, content: str) -> tuple[list[dict], dict | None]:
        """Call the local LLM for lead extraction. Returns (leads, doc_classification_or_None)."""
        try:
            from app.services.ai.model_manager import get_model_manager
            from app.config.settings import get_settings
            from app.services.ai.utils import extract_json_from_response

            cfg = get_settings()
            mm = get_model_manager()
            model_info = await mm.get_model("generator", cfg.GENERATOR_MODEL)
            loader = model_info["loader"] if isinstance(model_info, dict) else model_info

            user_prompt = EXTRACTION_USER_PROMPT_TEMPLATE.format(content=content)

            result = await loader.generate(
                prompt=user_prompt,
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                max_tokens=4096,
                temperature=0.1,
            )

            raw = result.text if hasattr(result, "text") else str(result)
            parsed = extract_json_from_response(raw)

            doc_classification = None
            leads = []

            if isinstance(parsed, dict):
                doc_classification = {
                    "type": parsed.get("document_type"),
                    "confidence": parsed.get("document_confidence"),
                    "reason": parsed.get("document_reason"),
                }
                raw_leads = parsed.get("leads", [])
                if isinstance(raw_leads, list):
                    leads = raw_leads
            elif isinstance(parsed, list):
                leads = parsed

            return leads, doc_classification

        except Exception as e:
            logger.warning("LLM extraction failed, falling back to heuristic: %s", e)
            return [], None

    def _normalize_lead(self, lead: dict) -> None:
        """Post-process a single lead: normalize fields, split names, recalculate confidence."""
        # Normalize contact fields
        if "email" in lead and isinstance(lead["email"], str):
            lead["email"] = normalize_email(lead["email"])
        if "phone" in lead:
            lead["phone"] = normalize_phone(lead.get("phone", ""))
        if "website" in lead:
            lead["website"] = normalize_website(lead.get("website", ""))

        # Normalize name fields
        full_name = lead.get("full_name")
        if full_name and isinstance(full_name, str) and not lead.get("first_name"):
            fn, ln = split_full_name(full_name)
            lead["first_name"] = fn
            lead["last_name"] = ln

        # Ensure confidence
        conf = lead.get("confidence")
        if not conf or not isinstance(conf, (int, float)):
            lead["confidence"] = calculate_confidence(lead)

        # Ensure confidence_reason
        if not lead.get("confidence_reason"):
            lead["confidence_reason"] = self._build_confidence_reason(lead)

    @staticmethod
    def _build_confidence_reason(lead: dict) -> str:
        parts = []
        if lead.get("email"):
            parts.append("email")
        if lead.get("phone"):
            parts.append("phone")
        if lead.get("first_name"):
            parts.append("name")
        if lead.get("company"):
            parts.append("company")
        if lead.get("linkedin") or lead.get("website"):
            parts.append("web presence")
        if not parts:
            return "Minimal data"
        return "Has " + ", ".join(parts)

    async def _enrich_leads(self, leads: list[dict]) -> list[dict]:
        """Enrich extracted leads by filling in missing fields.

        Runs rule-based enrichment first (fast, deterministic),
        then AI enrichment (batch LLM call for harder inferences).
        Both sets of results are merged into each lead.
        """
        if not leads:
            return leads

        # Phase A: Rule-based enrichment
        self._enrich_leads_rule_based(leads)

        # Phase B: AI enrichment
        try:
            await self._enrich_leads_ai(leads)
        except Exception as e:
            logger.warning("AI enrichment failed, rule-based results kept: %s", e)

        return leads

    @staticmethod
    def _enrich_leads_rule_based(leads: list[dict]) -> None:
        """Deterministic rule-based enrichment — no LLM call needed."""
        # Known free email providers — skip company inference from these
        free_email_domains = {
            "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
            "msn.com", "live.com", "aol.com", "mail.com", "protonmail.com",
            "icloud.com", "me.com", "yandex.com", "zoho.com", "gmx.com",
        }

        for lead in leads:
            email = (lead.get("email") or "").strip()
            phone = (lead.get("phone") or "").strip()
            enrichment_log: list[str] = []

            # ── Rule 1: Email domain → Website ──────────────────────────
            if email and not lead.get("website"):
                domain = email.split("@")[-1].strip().lower()
                if domain and "." in domain:
                    lead["website"] = f"https://{domain}"
                    enrichment_log.append(f"Inferred website {lead['website']} from email domain")

            # ── Rule 2: Email domain → Company name ─────────────────────
            if email and not lead.get("company"):
                domain = email.split("@")[-1].strip().lower()
                name_part = domain.split(".")[0] if "." in domain else domain
                if name_part and name_part not in {d.split(".")[0] for d in free_email_domains}:
                    # Skip common free email prefixes
                    common_prefixes = {"gmail", "yahoo", "hotmail", "outlook", "msn", "live",
                                       "aol", "mail", "protonmail", "icloud", "me", "yandex",
                                       "zoho", "gmx"}
                    if name_part not in common_prefixes:
                        lead["company"] = name_part.title()
                        enrichment_log.append(f"Inferred company '{lead['company']}' from email domain")

            # ── Rule 3: Phone country code → Country ────────────────────
            if phone and not lead.get("country"):
                country = LeadImportService._infer_country_from_phone(phone)
                if country:
                    lead["country"] = country
                    enrichment_log.append(f"Inferred country '{country}' from phone code")

            # ── Rule 4: Proper name casing ──────────────────────────────
            for field in ("first_name", "last_name", "city", "state", "country", "company"):
                val = lead.get(field)
                if val and isinstance(val, str) and len(val) > 1:
                    # Only apply if it looks like all-lowercase or all-uppercase
                    if val.isupper() or val.islower():
                        lead[field] = val.strip().title()

            # Store the enrichment log
            if enrichment_log:
                existing = lead.get("enrichment") or {}
                if isinstance(existing, dict):
                    existing.setdefault("log", [])
                    existing["log"].extend(enrichment_log)
                    lead["enrichment"] = existing
                else:
                    lead["enrichment"] = {"log": enrichment_log}

    async def _enrich_leads_ai(self, leads: list[dict]) -> None:
        """Use LLM to infer missing fields (industry, company size, designation, etc.)."""
        from app.services.ai.model_manager import get_model_manager
        from app.config.settings import get_settings
        from app.services.ai.utils import extract_json_from_response

        cfg = get_settings()
        mm = get_model_manager()
        model_info = await mm.get_model("generator", cfg.GENERATOR_MODEL)
        loader = model_info["loader"] if isinstance(model_info, dict) else model_info

        # Build a compact representation — only fields relevant for enrichment
        compact = []
        for lead in leads:
            entry = {}
            for key in ("first_name", "last_name", "company", "designation",
                        "email", "phone", "website", "industry", "city",
                        "state", "country", "notes"):
                entry[key] = lead.get(key)
            compact.append(entry)

        lead_data = json.dumps(compact, indent=2)

        result = await loader.generate(
            prompt=ENRICHMENT_USER_PROMPT_TEMPLATE.format(lead_data=lead_data),
            system_prompt=ENRICHMENT_SYSTEM_PROMPT,
            max_tokens=4096,
            temperature=0.1,
        )

        raw = result.text if hasattr(result, "text") else str(result)
        parsed = extract_json_from_response(raw)

        enriched_leads = []
        if isinstance(parsed, dict) and "leads" in parsed:
            enriched_leads = parsed["leads"]
        elif isinstance(parsed, list):
            enriched_leads = parsed

        if not enriched_leads or len(enriched_leads) != len(leads):
            logger.warning(
                "Enrichment returned %d leads, expected %d — skipping AI enrichment",
                len(enriched_leads), len(leads),
            )
            return

        for original, enriched in zip(leads, enriched_leads):
            enrichment_data = enriched.get("enrichment")
            if not enrichment_data or not isinstance(enrichment_data, dict):
                continue
            log_entries = enrichment_data.get("log", [])

            # Merge inferred fields into the original lead
            inferred_fields = {
                "inferred_company", "inferred_industry", "inferred_country",
                "inferred_company_size", "inferred_website", "inferred_designation",
            }
            lead_enrich = original.get("enrichment") or {}
            if isinstance(lead_enrich, dict):
                for field in inferred_fields:
                    val = enrichment_data.get(field)
                    if val:
                        lead_enrich[field] = val
                # Append new log entries
                existing_log = lead_enrich.setdefault("log", [])
                existing_log.extend(log for log in log_entries if log not in existing_log)
                original["enrichment"] = lead_enrich
            else:
                original["enrichment"] = enrichment_data

            # If the LLM confidently filled a missing field, apply it directly
            # Only apply inferred_company if original company was null
            if enrichment_data.get("inferred_company") and not original.get("company"):
                original["company"] = enrichment_data["inferred_company"]

            if enrichment_data.get("inferred_industry") and not original.get("industry"):
                original["industry"] = enrichment_data["inferred_industry"]

            if enrichment_data.get("inferred_country") and not original.get("country"):
                original["country"] = enrichment_data["inferred_country"]

            if enrichment_data.get("inferred_website") and not original.get("website"):
                original["website"] = enrichment_data["inferred_website"]

            if enrichment_data.get("inferred_designation") and not original.get("designation"):
                original["designation"] = enrichment_data["inferred_designation"]

    @staticmethod
    def _infer_country_from_phone(phone: str) -> str | None:
        """Map phone country codes to country names."""
        cleaned = re.sub(r"[^\d]", "", phone)
        if cleaned.startswith("+"):
            cleaned = cleaned[1:]
        elif cleaned.startswith("00"):
            cleaned = cleaned[2:]

        code_map: list[tuple[str, str]] = [
            ("1", "United States"),
            ("44", "United Kingdom"),
            ("91", "India"),
            ("86", "China"),
            ("49", "Germany"),
            ("33", "France"),
            ("81", "Japan"),
            ("82", "South Korea"),
            ("61", "Australia"),
            ("55", "Brazil"),
            ("7", "Russia"),
            ("39", "Italy"),
            ("34", "Spain"),
            ("31", "Netherlands"),
            ("41", "Switzerland"),
            ("46", "Sweden"),
            ("47", "Norway"),
            ("45", "Denmark"),
            ("358", "Finland"),
            ("48", "Poland"),
            ("90", "Turkey"),
            ("971", "UAE"),
            ("966", "Saudi Arabia"),
            ("65", "Singapore"),
            ("852", "Hong Kong"),
            ("886", "Taiwan"),
            ("27", "South Africa"),
            ("52", "Mexico"),
            ("54", "Argentina"),
            ("56", "Chile"),
            ("57", "Colombia"),
            ("60", "Malaysia"),
            ("62", "Indonesia"),
            ("63", "Philippines"),
            ("64", "New Zealand"),
            ("66", "Thailand"),
            ("351", "Portugal"),
            ("353", "Ireland"),
            ("354", "Iceland"),
            ("36", "Hungary"),
            ("38", "Ukraine"),
            ("40", "Romania"),
            ("420", "Czech Republic"),
            ("43", "Austria"),
            ("30", "Greece"),
            ("32", "Belgium"),
            ("972", "Israel"),
            ("20", "Egypt"),
            ("234", "Nigeria"),
            ("254", "Kenya"),
            ("233", "Ghana"),
        ]
        for code, country in code_map:
            if cleaned.startswith(code):
                return country
        return None

    def _store_doc_classification(self, job_id: UUID, classification: dict) -> None:
        """Store document classification metadata on the job."""
        job = self.repo.get_job(job_id)
        if not job:
            return
        stats = dict(job.statistics or {})
        stats["document_classification"] = {
            k: v for k, v in classification.items() if v is not None
        }
        job.statistics = stats
        self.repo.db.flush()

    def _heuristic_extract(self, doc: ExtractedDocument) -> list[dict]:
        """Enhanced heuristic extraction — never returns empty for CSV with data rows.

        Handles more column variants, text-based email/phone detection,
        and name splitting. Does NOT require an email column.
        """
        leads = []
        seen_keys: set[str] = set()

        # Build reverse map: normalized header -> canonical field name
        variant_to_field: dict[str, str] = {}
        for canonical, variants in HEURISTIC_COLUMN_MAP.items():
            for v in variants:
                variant_to_field[v] = canonical
        for canonical in ["full_name", "first_name", "last_name", "company", "email",
                          "phone", "website", "linkedin", "designation", "department",
                          "city", "state", "country", "postal_code", "industry", "notes"]:
            variant_to_field[canonical] = canonical

        def normalize_header(h: str) -> str:
            return h.lower().strip().replace("_", " ").replace("-", " ").strip()

        def get_field_from_row(field: str, idx_map: dict, row_list: list) -> str | None:
            idx = idx_map.get(field)
            if idx is not None and idx < len(row_list):
                val = row_list[idx].strip()
                return val if val else None
            return None

        # Phase A: extract from tables
        for ti, table in enumerate(doc.tables):
            if not table or len(table) < 2:
                continue

            header = [normalize_header(h) for h in table[0]]
            field_idx: dict[str, int] = {}
            for i, h in enumerate(header):
                if h and h in variant_to_field:
                    field_idx[variant_to_field[h]] = i

            logger.debug("Heuristic table %d: headers=%s, mapped=%s", ti, header, field_idx)

            if not field_idx:
                continue

            has_email = "email" in field_idx
            has_name = "full_name" in field_idx or "first_name" in field_idx
            if not has_email and not has_name:
                continue

            for ri, row in enumerate(table[1:]):
                # Build a unique key for dedup
                email_val = get_field_from_row("email", field_idx, row) or ""
                name_val = get_field_from_row("full_name", field_idx, row) or get_field_from_row("first_name", field_idx, row) or ""
                dedup_key = (email_val.lower(), name_val.lower().strip())
                if dedup_key in seen_keys:
                    continue
                if email_val and "@" in email_val:
                    seen_keys.add(dedup_key)
                elif name_val:
                    seen_keys.add(dedup_key)
                else:
                    continue

                lead: dict = {
                    "first_name": None,
                    "last_name": None,
                    "company": None,
                    "designation": None,
                    "department": None,
                    "email": email_val or None,
                    "phone": None,
                    "website": None,
                    "linkedin": None,
                    "city": None,
                    "state": None,
                    "country": None,
                    "postal_code": None,
                    "industry": None,
                    "notes": None,
                    "confidence": 0.5,
                    "confidence_reason": "Heuristic extraction",
                    "source_page": 1,
                    "source_row": ri + 2,
                    "document_section": f"table_{ti + 1}",
                    "duplicate_probability": 0,
                }

                full_name = get_field_from_row("full_name", field_idx, row)
                if full_name:
                    fn, ln = split_full_name(full_name)
                    lead["first_name"] = fn
                    lead["last_name"] = ln
                else:
                    lead["first_name"] = get_field_from_row("first_name", field_idx, row)
                    lead["last_name"] = get_field_from_row("last_name", field_idx, row)

                lead["company"] = get_field_from_row("company", field_idx, row)
                lead["designation"] = get_field_from_row("designation", field_idx, row)
                lead["department"] = get_field_from_row("department", field_idx, row)
                lead["phone"] = get_field_from_row("phone", field_idx, row)
                lead["website"] = get_field_from_row("website", field_idx, row)
                lead["linkedin"] = get_field_from_row("linkedin", field_idx, row)
                lead["city"] = get_field_from_row("city", field_idx, row)
                lead["state"] = get_field_from_row("state", field_idx, row)
                lead["country"] = get_field_from_row("country", field_idx, row)
                lead["postal_code"] = get_field_from_row("postal_code", field_idx, row)
                lead["industry"] = get_field_from_row("industry", field_idx, row)
                lead["notes"] = get_field_from_row("notes", field_idx, row)
                lead["confidence"] = calculate_confidence(lead)

                leads.append(lead)

        logger.debug("Heuristic table extraction produced %d leads", len(leads))

        # Phase B: extract from text if no table-based leads found
        if not leads and doc.text:
            leads_from_text = self._extract_from_text(doc.text)
            leads.extend(leads_from_text)
            logger.debug("Text fallback produced %d leads", len(leads_from_text))

        return leads

    @staticmethod
    def _extract_from_text(text: str) -> list[dict]:
        """Extract potential leads from unstructured text using regex."""
        leads = []
        email_pattern = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
        phone_pattern = re.compile(r"\+?\d[\d\s\-().]{7,}\d")
        seen_emails = set()

        for line in text.splitlines():
            line = line.strip()
            emails = email_pattern.findall(line)
            phones = phone_pattern.findall(line)

            if not emails:
                continue

            for email in emails:
                email_lower = email.lower()
                if email_lower in seen_emails:
                    continue
                seen_emails.add(email_lower)

                lead: dict = {
                    "first_name": None,
                    "last_name": None,
                    "company": None,
                    "designation": None,
                    "department": None,
                    "email": email_lower,
                    "phone": phones[0] if phones else None,
                    "website": None,
                    "linkedin": None,
                    "city": None,
                    "state": None,
                    "country": None,
                    "postal_code": None,
                    "industry": None,
                    "notes": line,
                    "confidence": 0.4,
                    "confidence_reason": "Text-based regex extraction",
                    "source_page": 1,
                    "source_row": None,
                    "document_section": "text",
                    "duplicate_probability": 0,
                }
                leads.append(lead)

        return leads

    def _validate_rows(self, job_id: UUID) -> None:
        """Validate all pending rows for the job."""
        rows = self.repo.get_rows_by_job(job_id, status=RowStatus.PENDING)
        for row in rows:
            extracted = row.extracted_data or {}
            if is_blank_row(extracted):
                self.repo.update_row(row.id, status=RowStatus.INVALID, error="Blank row", selected=False)
                continue
            errors = validate_lead_row(extracted)
            if errors:
                self.repo.update_row(row.id, status=RowStatus.INVALID, error="; ".join(errors), selected=False)

    def _deduplicate_rows(self, job_id: UUID) -> None:
        """Compare each valid row against the existing Lead table and classify."""
        job = self.repo.get_job(job_id)
        if not job:
            return

        rows = self.repo.get_rows_by_job(job_id, status=RowStatus.PENDING)

        for row in rows:
            extracted = row.extracted_data or {}
            email = (extracted.get("email") or "").strip()
            phone = (extracted.get("phone") or "").strip()

            matches = self.repo.find_matching_leads(job.tenant_id, email=email, phone=phone)

            if not matches:
                self.repo.update_row(row.id, status=RowStatus.NEW)
                continue

            email_lower = email.lower()
            phone_clean = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "").replace("+", "")

            email_match = any(
                str(getattr(m, "email", "")).lower() == email_lower
                for m in matches
            ) if email else False

            phone_match = any(
                str(getattr(m, "phone", "")).strip() == phone_clean
                for m in matches
            ) if phone_clean else False

            if email_match and phone_match:
                matched = next(
                    m for m in matches
                    if str(getattr(m, "email", "")).lower() == email_lower
                    and str(getattr(m, "phone", "")).strip() == phone_clean
                )
                self.repo.update_row(
                    row.id,
                    status=RowStatus.DUPLICATE,
                    duplicate=True,
                    duplicate_of=matched.id,
                    match_reason="email+phone",
                    selected=False,
                )
            elif email_match:
                matched = next(
                    m for m in matches
                    if str(getattr(m, "email", "")).lower() == email_lower
                )
                self.repo.update_row(
                    row.id,
                    status=RowStatus.UPDATE,
                    duplicate=True,
                    duplicate_of=matched.id,
                    match_reason="email",
                    selected=True,
                )
            elif phone_match:
                matched = next(
                    m for m in matches
                    if str(getattr(m, "phone", "")).strip() == phone_clean
                )
                self.repo.update_row(
                    row.id,
                    status=RowStatus.CONFLICT,
                    duplicate=True,
                    duplicate_of=matched.id,
                    match_reason="phone",
                    selected=False,
                )
            else:
                self.repo.update_row(
                    row.id,
                    status=RowStatus.NEW,
                )

    def _flag_review_rows(self, job_id: UUID) -> None:
        """Promote high-trust needs_review rows back to pending before further processing."""
        rows = self.repo.get_rows_by_job(job_id, status=RowStatus.NEEDS_REVIEW)
        for row in rows:
            extracted = row.extracted_data or {}
            intelligence = extracted.get("intelligence", {})
            trust_score = intelligence.get("trust_score", 50)
            completeness = intelligence.get("contact_completeness", 50)
            if trust_score >= 60 and completeness >= 40:
                self.repo.update_row(row.id, status=RowStatus.PENDING)

    def get_preview(self, job_id: UUID) -> dict:
        """Get the preview data for user review with dedup classifications."""
        job = self.repo.get_job(job_id)
        if not job:
            raise JobNotFoundError(str(job_id))
        if job.status not in (ImportStatus.PREVIEW_READY, ImportStatus.COMMITTED):
            raise JobNotReadyError(str(job_id), job.status, ImportStatus.PREVIEW_READY)

        rows = self.repo.get_rows_by_job(job_id)
        new_rows = [r for r in rows if r.status == RowStatus.NEW]
        update_rows = [r for r in rows if r.status == RowStatus.UPDATE]
        duplicate_rows = [r for r in rows if r.status == RowStatus.DUPLICATE]
        conflict_rows = [r for r in rows if r.status == RowStatus.CONFLICT]
        invalid_rows = [r for r in rows if r.status == RowStatus.INVALID]
        spam_rows = [r for r in rows if r.status == RowStatus.SPAM]
        needs_review_rows = [r for r in rows if r.status == RowStatus.NEEDS_REVIEW]
        skipped_rows = [r for r in rows if r.status == RowStatus.SKIPPED]

        # Extract document classification from job statistics
        doc_classification = None
        if job.statistics and "document_classification" in job.statistics:
            doc_classification = job.statistics["document_classification"]

        return {
            "job_id": str(job.id),
            "public_id": job.public_id,
            "filename": job.filename,
            "file_type": job.file_type,
            "status": job.status,
            "detected_columns": list(job.statistics.keys()) if job.statistics else [],
            "statistics": job.statistics,
            "total_rows": job.total_rows or 0,
            "document_classification": doc_classification,
            "new_rows": [_row_to_preview(r) for r in new_rows],
            "update_rows": [_row_to_preview(r) for r in update_rows],
            "duplicate_rows": [_row_to_preview(r) for r in duplicate_rows],
            "conflict_rows": [_row_to_preview(r) for r in conflict_rows],
            "invalid_rows": [_row_to_preview(r) for r in invalid_rows],
            "spam_rows": [_row_to_preview(r) for r in spam_rows],
            "needs_review_rows": [_row_to_preview(r) for r in needs_review_rows],
            "ignored_rows": [_row_to_preview(r) for r in skipped_rows],
        }

    def update_row_data(self, row_id: UUID, updates: dict) -> dict | None:
        """Edit a single row's extracted data. Sets user_edited flag to prevent overwrites."""
        row = self.repo.get_row(row_id)
        if not row:
            raise JobNotFoundError(str(row_id))
        extracted = dict(row.extracted_data or {})
        extracted.update(updates)
        extracted["user_edited"] = True
        self.repo.update_row(row_id, extracted_data=extracted)
        return _row_to_preview(row)

    def ignore_row(self, row_id: UUID) -> dict | None:
        """Mark a row as skipped/ignored."""
        row = self.repo.get_row(row_id)
        if not row:
            raise JobNotFoundError(str(row_id))
        self.repo.update_row(row_id, status=RowStatus.SKIPPED, selected=False)
        return _row_to_preview(row)

    def bulk_action(self, job_id: UUID, action: str, row_ids: list[UUID]) -> dict:
        """Perform a bulk action on multiple rows (ignore, reset, spam)."""
        count = 0
        for row_id in row_ids:
            row = self.repo.get_row(row_id)
            if not row or row.job_id != job_id:
                continue
            if action == "ignore":
                self.repo.update_row(row_id, status=RowStatus.SKIPPED, selected=False)
            elif action == "reset":
                self.repo.update_row(row_id, status=RowStatus.PENDING, selected=True)
            elif action == "spam":
                self.repo.update_row(row_id, status=RowStatus.SPAM, selected=False)
            elif action == "select":
                self.repo.update_row(row_id, selected=True)
            elif action == "deselect":
                self.repo.update_row(row_id, selected=False)
            count += 1
        self.repo.update_job_statistics(job_id)
        return {"action": action, "affected_rows": count}

    def commit(self, job_id: UUID) -> dict:
        """Commit selected rows into the Lead table.

        - NEW rows: insert fresh leads
        - UPDATE rows: merge changes into existing leads
        - DUPLICATE / CONFLICT rows: skipped unless user re-selects them
        """
        from app.models.leads.lead import Lead
        from app.domains.leads.events import build_lead_created_event
        from app.events import DomainEventPublisher, EVENT_LEAD_CREATED

        job = self.repo.get_job(job_id)
        if not job:
            raise JobNotFoundError(str(job_id))
        if job.status != ImportStatus.PREVIEW_READY:
            raise JobNotReadyError(str(job_id), job.status, ImportStatus.PREVIEW_READY)

        selected = self.repo.get_selected_rows(job_id)
        imported = 0
        imported_new = 0
        imported_updates = 0
        invalid_attempts = 0
        publisher = DomainEventPublisher(source="lead_import.service")

        pre_duplicates = self.repo.count_rows_by_status(job_id, RowStatus.DUPLICATE)
        pre_conflicts = self.repo.count_rows_by_status(job_id, RowStatus.CONFLICT)

        for row in selected:
            extracted = row.extracted_data or {}
            status = row.status

            if status == RowStatus.DUPLICATE:
                continue

            if status == RowStatus.CONFLICT:
                continue

            email = (extracted.get("email") or "").strip()
            if not email:
                invalid_attempts += 1
                self.repo.update_row(row.id, status=RowStatus.SKIPPED, error="No email after extraction")
                continue

            if status == RowStatus.UPDATE and row.duplicate_of:
                existing = self.repo.db.get(Lead, row.duplicate_of)
                if existing:
                    existing.first_name = (extracted.get("first_name") or "").strip() or existing.first_name
                    existing.last_name = (extracted.get("last_name") or "").strip() or existing.last_name
                    existing.company = (extracted.get("company") or "").strip() or existing.company
                    phone_str = extracted.get("phone") or ""
                    if phone_str:
                        try:
                            existing.phone = int("".join(c for c in str(phone_str) if c.isdigit())[:15])
                        except (ValueError, IndexError):
                            pass
                    self.repo.db.flush()
                    self.repo.update_row(row.id, status=RowStatus.COMMITTED, lead_id=existing.id)
                    publisher.publish(EVENT_LEAD_CREATED, str(job.tenant_id), {
                        "lead_id": str(existing.id),
                        "email": email,
                        "source": "import_update",
                        "import_job_id": str(job.id),
                    })
                    imported_updates += 1
                    imported += 1
                    continue

            lead = Lead(
                tenant_id=job.tenant_id,
                email=email,
                first_name=(extracted.get("first_name") or "").strip() or None,
                last_name=(extracted.get("last_name") or "").strip() or None,
                company=(extracted.get("company") or "").strip() or None,
                phone=extracted.get("phone") or "",
                status="new",
            )
            self.repo.db.add(lead)
            self.repo.db.flush()

            self.repo.update_row(row.id, status=RowStatus.COMMITTED, lead_id=lead.id)

            publisher.publish(EVENT_LEAD_CREATED, str(job.tenant_id), {
                "lead_id": str(lead.id),
                "email": email,
                "source": "import",
                "import_job_id": str(job.id),
            })
            imported_new += 1
            imported += 1

        self.repo.update_job_status(job.id, ImportStatus.COMMITTED, completed_at=None)
        self.repo.update_job_statistics(job.id)

        return {
            "job_id": str(job.id),
            "public_id": job.public_id,
            "status": ImportStatus.COMMITTED,
            "total_imported": imported,
            "total_new": imported_new,
            "total_updated": imported_updates,
            "total_duplicates": pre_duplicates,
            "total_conflicts": pre_conflicts,
            "total_invalid": invalid_attempts,
            "message": f"Imported {imported} leads ({imported_new} new, {imported_updates} updates); {pre_duplicates} duplicates, {pre_conflicts} conflicts, {invalid_attempts} invalid",
        }


def _row_to_preview(row: LeadImportRow) -> dict:
    extracted = row.extracted_data or {}
    quality = extracted.get("quality") or {}
    intelligence = extracted.get("intelligence")
    return {
        "id": str(row.id),
        "row_index": row.row_index,
        "raw_data": row.raw_data or {},
        "normalized_data": row.normalized_data or {},
        "extracted_data": extracted,
        "confidence": row.confidence,
        "confidence_reason": extracted.get("confidence_reason"),
        "duplicate_probability": extracted.get("duplicate_probability"),
        "source_page": extracted.get("source_page"),
        "source_row": extracted.get("source_row"),
        "quality_score": quality.get("score"),
        "quality_grade": quality.get("grade"),
        "quality_reasons": quality.get("reasons"),
        "quality_flags": quality.get("flags"),
        "intelligence": intelligence,
        "duplicate": row.duplicate,
        "duplicate_of": str(row.duplicate_of) if row.duplicate_of else None,
        "match_reason": row.match_reason,
        "status": row.status,
        "selected": row.selected,
        "error": row.error,
    }
