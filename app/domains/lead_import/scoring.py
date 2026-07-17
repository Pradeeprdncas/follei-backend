"""Lead Quality Scoring for the Lead Import pipeline.

Each extracted lead receives a 0-100 quality score with grade, reasons, and flags.
This is an import quality score only — separate from CRM lead scoring.
"""

FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.co.in", "yahoo.co.uk", "hotmail.com",
    "outlook.com", "msn.com", "live.com", "live.co.uk", "aol.com",
    "mail.com", "protonmail.com", "proton.me", "icloud.com", "me.com",
    "yandex.com", "yandex.ru", "zoho.com", "gmx.com", "gmx.net",
    "fastmail.com", "tutanota.com", "tutamail.com", "rediffmail.com",
    "rediffmailpro.com", "lycos.com", "mail.ru", "inbox.com",
}

DISPOSABLE_EMAIL_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com",
    "tempmail.com", "throwaway.email", "yopmail.com", "sharklasers.com",
    "temp-mail.org", "trashmail.com", "maildrop.cc", "getairmail.com",
    "fakemailgenerator.com", "spambox.us", "dispostable.com",
    "mailnator.com", "temp-mail.io", "tempmail.net", "emailondeck.com",
    "guerrillamail.org", "burnermail.io", "mytemp.email", "tempemail.net",
    "spamgourmet.com", "mailmetrash.com", "spambox.me",
    "nepwk.com", "temporary-mail.net", "emailtemporal.com",
}


def calculate_quality_score(lead: dict) -> dict:
    """Calculate a 0-100 quality score for a single lead record.

    Returns a dict with keys: score (int), grade (str),
    reasons (list[str]), flags (list[str]).
    """
    score = 50
    reasons: list[str] = []
    flags: list[str] = []

    email = (lead.get("email") or "").strip()
    phone = (lead.get("phone") or "").strip()
    first_name = (lead.get("first_name") or "").strip()
    last_name = (lead.get("last_name") or "").strip()
    company = (lead.get("company") or "").strip()
    website = (lead.get("website") or "").strip()
    linkedin = (lead.get("linkedin") or "").strip()
    designation = (lead.get("designation") or "").strip()
    industry = (lead.get("industry") or "").strip()
    country = (lead.get("country") or "").strip()
    duplicate_prob = lead.get("duplicate_probability") or 0
    ai_confidence = lead.get("confidence") or 0

    # ── Name ───────────────────────────────────────────────────────────
    if first_name:
        score += 10
        reasons.append("First name present")
    if last_name:
        score += 5
        reasons.append("Last name present")
    if first_name and not last_name:
        score -= 5
        reasons.append("Only one name part")

    # ── Email ──────────────────────────────────────────────────────────
    if email:
        domain = email.split("@")[-1].lower() if "@" in email else ""
        if domain in DISPOSABLE_EMAIL_DOMAINS:
            score -= 40
            reasons.append("Disposable email detected")
            flags.append("DISPOSABLE_EMAIL")
        elif domain in FREE_EMAIL_DOMAINS:
            score += 5
            reasons.append("Free email detected")
            flags.append("FREE_EMAIL")
        else:
            score += 20
            reasons.append("Corporate email detected")
            flags.append("CORPORATE_EMAIL")
    else:
        flags.append("INVALID_EMAIL")

    # ── Phone ──────────────────────────────────────────────────────────
    if phone:
        digits = [c for c in phone if c.isdigit()]
        if len(digits) >= 7:
            score += 15
            reasons.append("Phone validated")
        else:
            score -= 15
            reasons.append("Invalid phone")
            flags.append("INVALID_PHONE")
    else:
        score -= 10
        reasons.append("Missing phone")
        flags.append("MISSING_PHONE")

    # ── Company ────────────────────────────────────────────────────────
    if company:
        score += 15
        reasons.append("Company identified")
    else:
        score -= 15
        reasons.append("Missing company")
        flags.append("MISSING_COMPANY")

    # ── Website ────────────────────────────────────────────────────────
    if website:
        score += 10
        reasons.append("Website found")
        if email:
            email_domain = email.split("@")[-1].lower() if "@" in email else ""
            if email_domain and email_domain in website.lower():
                score += 10
                reasons.append("Corporate domain matches email")

    # ── LinkedIn ───────────────────────────────────────────────────────
    if linkedin:
        score += 10
        reasons.append("LinkedIn found")

    # ── Designation ────────────────────────────────────────────────────
    if designation:
        score += 5
        reasons.append("Designation present")

    # ── Industry ───────────────────────────────────────────────────────
    if industry:
        score += 5
        reasons.append("Industry present")

    # ── Country ────────────────────────────────────────────────────────
    if country:
        score += 3
        reasons.append("Country present")

    # ── Duplicate probability penalty ─────────────────────────────────
    if isinstance(duplicate_prob, (int, float)) and duplicate_prob > 0:
        if duplicate_prob > 80:
            score -= 25
            reasons.append("Likely duplicate (high probability)")
            flags.append("LIKELY_DUPLICATE")
        elif duplicate_prob > 50:
            score -= 10
            reasons.append("Possible duplicate")

    # ── AI Confidence bonus / penalty ─────────────────────────────────
    if isinstance(ai_confidence, (int, float)):
        if ai_confidence > 0.9:
            score += 10
            reasons.append("High AI confidence")
        elif ai_confidence > 0.7:
            score += 5
            reasons.append("Good AI confidence")
        elif ai_confidence < 0.5:
            score -= 15
            reasons.append("Low AI confidence")
            flags.append("LOW_CONFIDENCE")

    # ── Clamp ──────────────────────────────────────────────────────────
    score = max(0, min(100, score))

    # ── Grade ──────────────────────────────────────────────────────────
    if score >= 90:
        grade = "A"
    elif score >= 80:
        grade = "B"
    elif score >= 65:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"

    # ── Additional flags ───────────────────────────────────────────────
    missing_important = sum(1 for f in [company, phone, first_name, email] if not f)
    if missing_important >= 3:
        flags.append("INCOMPLETE")
    if score < 40:
        flags.append("LOW_INFORMATION")

    return {
        "score": score,
        "grade": grade,
        "reasons": list(dict.fromkeys(reasons)),
        "flags": list(set(flags)),
    }


def compute_quality_statistics(leads: list[dict]) -> dict:
    """Compute aggregate quality statistics from a list of lead records.

    Each lead must have a "quality" key with the output of calculate_quality_score.
    """
    scores: list[int] = []
    grades: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    confidences: list[float] = []
    corporate_email_count = 0
    free_email_count = 0
    incomplete_count = 0

    for lead in leads:
        quality = lead.get("quality") or {}
        score = quality.get("score")
        if score is not None:
            scores.append(score)
        grade = quality.get("grade")
        if grade and grade in grades:
            grades[grade] += 1

        flags = quality.get("flags", []) or []
        if "INCOMPLETE" in flags:
            incomplete_count += 1

        conf = lead.get("confidence")
        if isinstance(conf, (int, float)):
            confidences.append(conf)

        # Classify email type from the raw lead data
        email = (lead.get("email") or "").strip()
        if email:
            domain = email.split("@")[-1].lower() if "@" in email else ""
            if domain not in FREE_EMAIL_DOMAINS and domain not in DISPOSABLE_EMAIL_DOMAINS:
                corporate_email_count += 1
            elif domain in FREE_EMAIL_DOMAINS:
                free_email_count += 1

    if not scores:
        return {
            "average_score": 0,
            "highest_score": 0,
            "lowest_score": 0,
            "grade_distribution": grades,
            "average_confidence": 0.0,
            "corporate_email_count": 0,
            "free_email_count": 0,
            "incomplete_count": 0,
            "total_scored": 0,
        }

    return {
        "average_score": round(sum(scores) / len(scores), 1),
        "highest_score": max(scores),
        "lowest_score": min(scores),
        "grade_distribution": grades,
        "average_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
        "corporate_email_count": corporate_email_count,
        "free_email_count": free_email_count,
        "incomplete_count": incomplete_count,
        "total_scored": len(scores),
    }
