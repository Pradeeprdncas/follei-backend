from app.analysis.services.llm_qualification_service import LLMQualificationService


def test_bant_fallback_scores_only_transcript_evidence():
    transcript = "I have a budget of 50000 dollars, I am the decision maker, and we need this deployed this quarter."
    result = LLMQualificationService._fallback(
        transcript,
        "BANT",
        LLMQualificationService.get_components("BANT"),
        error="model unavailable",
    )

    assert result["source"] == "evidence_heuristic"
    assert result["status"] == "completed"
    assert all(result["scores"][name]["score"] > 0 for name in ("budget", "authority", "need", "timeline"))
    assert all(result["scores"][name]["evidence"] for name in ("budget", "authority", "need", "timeline"))


def test_meddic_fallback_uses_zero_for_missing_evidence_not_invented_values():
    result = LLMQualificationService._fallback(
        "We need to reduce processing time by 30 percent. Our procurement committee will run a pilot.",
        "MEDDIC",
        LLMQualificationService.get_components("MEDDIC"),
    )

    assert result["scores"]["metrics"]["score"] > 0
    assert result["scores"]["decision_process"]["score"] > 0
    assert result["scores"]["champion"] == {"score": 0.0, "evidence": ""}
    assert result["overall_score"] is not None
