from app.analysis.services.revenue_intelligence_service import RevenueIntelligenceService


def test_revenue_score_requires_evidence():
    assert RevenueIntelligenceService.analyze("Hello, nice to meet you.")["revenue_score"] == 0


def test_revenue_score_uses_conversation_and_crm_evidence():
    result = RevenueIntelligenceService.analyze(
        "We need 20% cost savings and have a ₹5 lakh budget this quarter.",
        crm_context={"deal_value": 500000},
    )
    assert result["revenue_score"] >= 70
    assert result["monetary_evidence"] == ["₹5 lakh"]
    assert result["structured_opportunity_value"] == 500000
