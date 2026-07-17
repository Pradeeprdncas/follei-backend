"""Lead Intelligence engine — enriches extracted leads with spam detection,
business classification, email/phone/company intelligence, trust scoring,
authority inference, recommended action, and AI summary.

Runs after Company Enrichment and before Quality Scoring in the pipeline.

All output stored in extracted_data.intelligence (JSONB, no migration needed).
"""

import re

# ── Constants ──────────────────────────────────────────────────────────

FAKE_NAME_PATTERNS = {
    "asdf", "qwerty", "test", "testuser", "user", "admin",
    "abc", "xyz", "foo", "bar", "baz", "demo", "sample",
    "test123", "testing", "tester", "guest", "root", "null",
    "undefined", "na", "n/a", "none", "delete", "remove",
    "aaaa", "bbbb", "cccc", "1234", "12345", "123456",
}

LOREM_WORDS = {"lorem", "ipsum", "dolor", "sit", "amet", "consectetur"}

BIZ_TITLES = {
    "ceo", "cto", "cfo", "coo", "cio", "cmo", "chief", "founder",
    "co-founder", "cofounder", "owner", "president", "vp", "vice president",
    "director", "head", "lead", "senior", "manager", "supervisor",
    "engineer", "developer", "architect", "administrator", "coordinator",
    "executive", "partner", "principal", "staff", "specialist",
    "sales", "marketing", "hr", "operations", "support", "analyst",
    "consultant", "advisor", "representative", "associate", "agent",
}

TECH_TITLES = {
    "engineer", "developer", "architect", "programmer", "software",
    "devops", "backend", "frontend", "full stack", "data", "ml",
    "ai", "machine learning", "infrastructure", "platform", "sre",
}

SALES_TITLES = {
    "sales", "account executive", "ae", "business development",
    "bd", "account manager", "customer success", "sdr", "bdr",
    "revenue", "growth",
}

STUDENT_KEYWORDS = {"student", "intern", "trainee", "scholar", "graduate", "phd", "ph.d"}

AUTHORITY_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bco-founder\b|\bcofounder\b", re.IGNORECASE), "Co-Founder"),
    (re.compile(r"\bfounder\b", re.IGNORECASE), "Founder"),
    (re.compile(r"\b(ceo|chief executive)\b", re.IGNORECASE), "CEO"),
    (re.compile(r"\b(president|owner)\b", re.IGNORECASE), "President"),
    (re.compile(r"\b(cto|chief technology|chief technical)\b", re.IGNORECASE), "CTO"),
    (re.compile(r"\b(cfo|chief financial)\b", re.IGNORECASE), "CFO"),
    (re.compile(r"\b(cio|chief information|chief digital)\b", re.IGNORECASE), "CIO"),
    (re.compile(r"\b(cmo|chief marketing)\b", re.IGNORECASE), "CMO"),
    (re.compile(r"\b(coo|chief operating)\b", re.IGNORECASE), "COO"),
    (re.compile(r"\bvice president\b|\bvp\b(?!\s+of\s+engineering)", re.IGNORECASE), "VP"),
    (re.compile(r"\bdirector\b", re.IGNORECASE), "Director"),
    (re.compile(r"\bhead of\b", re.IGNORECASE), "Head"),
    (re.compile(r"\bsenior\s+(manager|engineer|developer)\b", re.IGNORECASE), "Senior Manager"),
    (re.compile(r"\b(manager|supervisor)\b", re.IGNORECASE), "Manager"),
    (re.compile(r"\b(sales|account executive)\b", re.IGNORECASE), "Sales"),
    (re.compile(r"\b(hr|human resources|recruiter|talent)\b", re.IGNORECASE), "HR"),
    (re.compile(r"\b(support|customer success|customer service)\b", re.IGNORECASE), "Support"),
    (re.compile(r"\b(engineer|developer|architect|programmer)\b", re.IGNORECASE), "Engineer"),
    (re.compile(r"\b(analyst|consultant)\b", re.IGNORECASE), "Analyst"),
    (re.compile(r"\b(student|intern|trainee)\b", re.IGNORECASE), "Intern"),
]

ROLE_EMAIL_PREFIXES = {
    "support", "sales", "admin", "info", "noreply", "no-reply",
    "contact", "hello", "help", "feedback", "team", "careers",
    "jobs", "hr", "billing", "accounts", "marketing", "press",
    "media", "pr", "newsletter", "blog", "mail", "enquiries",
    "orders", "shipping", "returns",
}

# ── Spam Detection ─────────────────────────────────────────────────────

def detect_spam(lead: dict) -> dict:
    """Detect spam signals and return spam_score (0-100), probability, is_spam, reasons."""
    score = 0
    reasons: list[str] = []

    email = (lead.get("email") or "").strip()
    phone = (lead.get("phone") or "").strip()
    first_name = (lead.get("first_name") or "").strip()
    last_name = (lead.get("last_name") or "").strip()
    company = (lead.get("company") or "").strip()
    notes = (lead.get("notes") or "").strip()

    # Disposable / invalid email
    if email:
        if "@" not in email:
            score += 30
            reasons.append("Invalid email format")
        else:
            domain = email.split("@")[-1].lower()
            from app.domains.lead_import.scoring import DISPOSABLE_EMAIL_DOMAINS
            if domain in DISPOSABLE_EMAIL_DOMAINS:
                score += 40
                reasons.append("Disposable email")

    # Fake name patterns
    for name_part in [first_name, last_name]:
        if name_part.lower() in FAKE_NAME_PATTERNS:
            score += 25
            reasons.append("Suspicious name pattern")
            break

    # Lorem ipsum
    combined = f"{first_name} {last_name} {notes}".lower()
    if any(w in combined for w in LOREM_WORDS):
        score += 30
        reasons.append("Lorem ipsum detected")

    # All-numeric name
    if first_name and first_name.isdigit():
        score += 20
        reasons.append("Numeric name")

    # Random string (no vowels in first name longer than 2 chars)
    if first_name and len(first_name) > 2 and not re.search(r"[aeiouy]", first_name.lower()):
        score += 20
        reasons.append("Random string pattern in name")

    # Repeated value (email local part matches full name exactly)
    if email and "@" in email:
        local = email.split("@")[0].lower()
        full = f"{first_name}{last_name}".lower().replace(" ", "")
        if full and local == full:
            score += 10
            reasons.append("Email matches name exactly")

    # Garbage OCR (high non-alphanumeric ratio in notes)
    if notes and len(notes) > 10:
        non_alnum = sum(1 for c in notes if not c.isalnum() and not c.isspace())
        if non_alnum / len(notes) > 0.3:
            score += 15
            reasons.append("Garbage OCR detected")

    # Missing required contact info
    if not email and not phone:
        score += 15
        reasons.append("Missing contact info")

    # Empty or placeholder company
    if company and company.lower() in {"na", "n/a", "none", "-", "--", "null", "undefined", "."}:
        score += 10
        reasons.append("Placeholder company")

    score = min(100, max(0, score))
    return {
        "score": score,
        "probability": round(score / 100, 2),
        "is_spam": score > 50,
        "reasons": reasons,
    }


# ── Business Detection ─────────────────────────────────────────────────

def detect_business(lead: dict) -> dict:
    """Determine if a lead is business or personal contact."""
    from app.domains.lead_import.scoring import FREE_EMAIL_DOMAINS, DISPOSABLE_EMAIL_DOMAINS

    email = (lead.get("email") or "").strip()
    company = (lead.get("company") or "").strip()
    designation = (lead.get("designation") or "").strip()

    business_signals = 0.0
    personal_signals = 0.0

    if email and "@" in email:
        domain = email.split("@")[-1].lower()
        if domain not in FREE_EMAIL_DOMAINS and domain not in DISPOSABLE_EMAIL_DOMAINS:
            business_signals += 3.0
        elif domain in FREE_EMAIL_DOMAINS:
            personal_signals += 2.0 if not company else 0.5

    if company:
        business_signals += 3.0

    if designation:
        des_lower = designation.lower()
        if any(t in des_lower for t in BIZ_TITLES):
            business_signals += 2.0
        if any(s in des_lower for s in STUDENT_KEYWORDS):
            personal_signals += 2.0

    total = business_signals + personal_signals
    if total == 0:
        return _biz_result(0.5, 0.5, "Unknown")

    business_prob = round(business_signals / total, 2)
    person_prob = round(personal_signals / total, 2)

    if business_prob > 0.6:
        des_lower = (designation or "").lower()
        if any(t in des_lower for t in ["founder", "ceo", "owner", "president", "co-founder"]):
            lt = "Business Decision Maker"
        elif any(t in des_lower for t in ["manager", "director", "head", "vp"]):
            lt = "Business Manager"
        elif any(t in des_lower for t in TECH_TITLES):
            lt = "Technical Professional"
        elif any(t in des_lower for t in SALES_TITLES):
            lt = "Sales Professional"
        else:
            lt = "Business Contact"
    elif person_prob > 0.6:
        lt = "Personal Contact"
    else:
        lt = "Unknown"

    return _biz_result(business_prob, person_prob, lt)


def _biz_result(business_prob: float, person_prob: float, lead_type: str) -> dict:
    return {
        "probability": business_prob,
        "is_business": business_prob > 0.6,
        "person_probability": person_prob,
        "is_person": person_prob > 0.6,
        "lead_type": lead_type,
    }


# ── Email Intelligence ─────────────────────────────────────────────────

def analyze_email(lead: dict) -> dict:
    """Classify email type (Corporate, Free, Disposable, Role)."""
    from app.domains.lead_import.scoring import FREE_EMAIL_DOMAINS, DISPOSABLE_EMAIL_DOMAINS

    email = (lead.get("email") or "").strip()
    if not email or "@" not in email:
        return {"type": "Invalid", "valid": False}

    local = email.split("@")[0].lower()
    domain = email.split("@")[-1].lower()

    if domain in DISPOSABLE_EMAIL_DOMAINS:
        return {"type": "Disposable", "valid": False}
    if local in ROLE_EMAIL_PREFIXES:
        return {"type": local.capitalize(), "valid": True}
    if domain in FREE_EMAIL_DOMAINS:
        return {"type": "Free", "valid": True}
    return {"type": "Corporate", "valid": True}


# ── Phone Intelligence ─────────────────────────────────────────────────

COUNTRY_CODE_MAP: list[tuple[str, str, str]] = [
    ("1", "US", "United States"),
    ("44", "GB", "United Kingdom"),
    ("91", "IN", "India"),
    ("86", "CN", "China"),
    ("49", "DE", "Germany"),
    ("33", "FR", "France"),
    ("81", "JP", "Japan"),
    ("82", "KR", "South Korea"),
    ("61", "AU", "Australia"),
    ("55", "BR", "Brazil"),
    ("7", "RU", "Russia"),
    ("39", "IT", "Italy"),
    ("34", "ES", "Spain"),
    ("31", "NL", "Netherlands"),
    ("41", "CH", "Switzerland"),
    ("46", "SE", "Sweden"),
    ("47", "NO", "Norway"),
    ("45", "DK", "Denmark"),
    ("358", "FI", "Finland"),
    ("48", "PL", "Poland"),
    ("90", "TR", "Turkey"),
    ("971", "AE", "UAE"),
    ("966", "SA", "Saudi Arabia"),
    ("65", "SG", "Singapore"),
    ("852", "HK", "Hong Kong"),
    ("886", "TW", "Taiwan"),
    ("27", "ZA", "South Africa"),
    ("52", "MX", "Mexico"),
    ("54", "AR", "Argentina"),
    ("56", "CL", "Chile"),
    ("57", "CO", "Colombia"),
    ("60", "MY", "Malaysia"),
    ("62", "ID", "Indonesia"),
    ("63", "PH", "Philippines"),
    ("64", "NZ", "New Zealand"),
    ("66", "TH", "Thailand"),
    ("351", "PT", "Portugal"),
    ("353", "IE", "Ireland"),
    ("36", "HU", "Hungary"),
    ("40", "RO", "Romania"),
    ("420", "CZ", "Czech Republic"),
    ("43", "AT", "Austria"),
    ("30", "GR", "Greece"),
    ("32", "BE", "Belgium"),
    ("972", "IL", "Israel"),
    ("20", "EG", "Egypt"),
    ("234", "NG", "Nigeria"),
    ("254", "KE", "Kenya"),
    ("233", "GH", "Ghana"),
]

MOBILE_PREFIXES = {"6", "7", "8", "9"}


def analyze_phone(lead: dict) -> dict:
    """Validate phone and detect country, code, type."""
    phone = (lead.get("phone") or "").strip()
    if not phone:
        return {"valid": False, "country": None, "country_code": None, "type": "Unknown"}

    digits = re.sub(r"[^\d]", "", phone)
    if not digits:
        return {"valid": False, "country": None, "country_code": None, "type": "Unknown"}

    clean = digits
    if clean.startswith("+"):
        clean = clean[1:]
    elif clean.startswith("00"):
        clean = clean[2:]
    if clean.startswith("0"):
        clean = clean[1:]

    valid = 7 <= len(digits) <= 15
    country_code = None
    country = None

    for code, iso, name in COUNTRY_CODE_MAP:
        if clean.startswith(code):
            country_code = code
            country = name
            if code == "1":
                # For US/CA, remaining digits after country code
                remaining = clean[len(code):]
            break

    # Simple mobile detection: starts with 6/7/8/9 after country code
    remaining_after_code = clean
    if country_code:
        remaining_after_code = clean[len(country_code):]

    is_mobile = bool(remaining_after_code and remaining_after_code[0] in MOBILE_PREFIXES and valid)

    return {
        "valid": valid,
        "country": country,
        "country_code": f"+{country_code}" if country_code else None,
        "type": "Mobile" if is_mobile and valid else ("Landline" if valid else "Invalid"),
        "whatsapp_possible": valid,
    }


# ── Company Intelligence ───────────────────────────────────────────────

def analyze_company(lead: dict) -> dict:
    """Detect company existence, website, size category, LinkedIn."""
    company = (lead.get("company") or "").strip()
    website = (lead.get("website") or "").strip()
    linkedin = (lead.get("linkedin") or "").strip()

    exists = bool(company)
    website_exists = bool(website)
    linkedin_found = bool(linkedin)

    size = "Unknown"
    if company:
        company_lower = company.lower()
        if any(kw in company_lower for kw in ["startup", "venture", "seed", "incubat"]):
            size = "Likely Startup"
        elif any(kw in company_lower for kw in ["llc", "ltd", "inc", "corp", "gmbh", "pvt"]):
            size = "Likely SME"
        elif any(kw in company_lower for kw in ["global", "international", "group", "holdings", "enterprise"]):
            size = "Likely Enterprise"

    return {
        "exists": exists,
        "website_exists": website_exists,
        "linkedin_found": linkedin_found,
        "size": size,
    }


# ── Contact Completeness ───────────────────────────────────────────────

def compute_completeness(lead: dict) -> dict:
    """Calculate contact completeness as a percentage (0-100)."""
    fields = ["first_name", "last_name", "company", "email", "phone",
              "website", "linkedin", "country", "industry", "designation"]
    filled = sum(1 for f in fields if (lead.get(f) or "").strip())
    score = round((filled / len(fields)) * 100)
    return {"score": score, "filled": filled, "total": len(fields)}


# ── Trust Score ────────────────────────────────────────────────────────

def compute_trust_score(lead: dict, spam: dict, completeness: dict) -> dict:
    """Calculate a 0-100 trust score based on positive and negative signals."""
    score = 50.0
    email = (lead.get("email") or "").strip()
    phone = (lead.get("phone") or "").strip()
    company = (lead.get("company") or "").strip()
    website = (lead.get("website") or "").strip()
    linkedin = (lead.get("linkedin") or "").strip()
    confidence = lead.get("confidence") or 0
    dup_prob = lead.get("duplicate_probability") or 0

    # Positive signals
    from app.domains.lead_import.scoring import FREE_EMAIL_DOMAINS, DISPOSABLE_EMAIL_DOMAINS
    if email and "@" in email:
        domain = email.split("@")[-1].lower()
        if domain not in FREE_EMAIL_DOMAINS and domain not in DISPOSABLE_EMAIL_DOMAINS:
            score += 25
    if phone and len(re.sub(r"[^\d]", "", phone)) >= 7:
        score += 20
    if website:
        score += 15
    if company:
        score += 15
    if linkedin:
        score += 15

    if isinstance(confidence, (int, float)):
        if confidence > 0.9:
            score += 10
        elif confidence > 0.7:
            score += 5

    # Negative signals
    score -= spam["score"] * 0.5
    if isinstance(dup_prob, (int, float)):
        if dup_prob > 80:
            score -= 25
        elif dup_prob > 50:
            score -= 10

    score = max(0, min(100, round(score)))
    return {"score": score}


# ── Authority Detection ────────────────────────────────────────────────

def detect_authority(lead: dict) -> dict:
    """Infer authority/role from designation and other fields."""
    designation = (lead.get("designation") or "").strip()
    company = (lead.get("company") or "").strip()

    if not designation:
        return {"role": "Unknown", "confidence": "low"}

    for pattern, role in AUTHORITY_MAP:
        if pattern.search(designation):
            return {"role": role, "confidence": "high"}

    return {"role": "Unknown", "confidence": "low"}


# ── Recommended Action ─────────────────────────────────────────────────

def recommend_action(spam: dict, trust: dict, completeness: dict) -> dict:
    """Determine the recommended action for the lead."""
    trust_score = trust.get("score", 50)

    if spam["is_spam"]:
        return {"action": "Likely Spam", "reason": "Spam detected"}
    if spam["score"] > 30:
        return {"action": "Needs Correction", "reason": "Suspicious patterns detected"}
    if trust_score >= 70:
        return {"action": "Import", "reason": "High trust score"}
    if trust_score >= 40:
        return {"action": "Import & Review", "reason": "Moderate trust score"}
    if completeness["score"] < 30:
        return {"action": "Needs Correction", "reason": "Insufficient data"}
    return {"action": "Needs Correction", "reason": "Low trust score"}


# ── AI Summary ─────────────────────────────────────────────────────────

def generate_summary(lead: dict, authority: dict, business: dict, company_intel: dict) -> str:
    """Generate a one-sentence summary of the lead."""
    parts: list[str] = []
    role = authority.get("role", "Unknown")
    company = (lead.get("company") or "").strip()
    industry = (lead.get("industry") or "").strip()
    city = (lead.get("city") or "").strip()
    country = (lead.get("country") or "").strip()
    designation = (lead.get("designation") or "").strip()

    if business.get("is_business"):
        if role != "Unknown":
            if company:
                parts.append(role)
                if industry:
                    parts.append(f"at a {industry.lower()} company")
                else:
                    parts.append(f"at {company}")
            else:
                parts.append(role)
                parts.append("in business")
        elif designation:
            if company:
                parts.append(f"{designation} at {company}")
            else:
                parts.append(designation)
        elif company:
            parts.append(f"Professional at {company}")
        else:
            parts.append("Business contact")
    else:
        if city and country:
            parts.append(f"Personal contact from {city}, {country}")
        elif country:
            parts.append(f"Personal contact from {country}")
        elif city:
            parts.append(f"Personal contact from {city}")
        else:
            parts.append("Personal contact")

    if company_intel.get("size") and company_intel["size"] != "Unknown":
        size_word = company_intel["size"].replace("Likely ", "").lower()
        if parts:
            parts.append(f"({size_word})")

    summary = " ".join(parts) if parts else "Contact record"
    return summary.rstrip(".") + "."


# ── Main Orchestrator ──────────────────────────────────────────────────

def compute_lead_intelligence(lead: dict) -> dict:
    """Compute the full intelligence profile for a single lead."""
    spam = detect_spam(lead)
    business = detect_business(lead)
    email_intel = analyze_email(lead)
    phone_intel = analyze_phone(lead)
    company_intel = analyze_company(lead)
    completeness = compute_completeness(lead)
    trust = compute_trust_score(lead, spam, completeness)
    authority = detect_authority(lead)
    action = recommend_action(spam, trust, completeness)
    summary = generate_summary(lead, authority, business, company_intel)

    return {
        "spam_score": spam["score"],
        "spam_probability": spam["probability"],
        "is_spam": spam["is_spam"],
        "business_probability": business["probability"],
        "is_business": business["is_business"],
        "person_probability": business["person_probability"],
        "is_person": business["is_person"],
        "lead_type": business["lead_type"],
        "email_type": email_intel["type"],
        "company_exists": company_intel["exists"],
        "website_exists": company_intel["website_exists"],
        "linkedin_found": company_intel["linkedin_found"],
        "phone_valid": phone_intel["valid"],
        "contact_completeness": completeness["score"],
        "trust_score": trust["score"],
        "intent": "Unknown",
        "authority": authority["role"],
        "freshness": "Unknown",
        "recommended_action": action["action"],
        "summary": summary,
    }
