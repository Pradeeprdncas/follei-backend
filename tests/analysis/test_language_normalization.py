from app.analysis.pipelines.language_service import LanguageService
from app.services.rag.pipelines.chat import _language_instruction


def test_provider_iso3_codes_are_normalized_for_reply_language():
    assert LanguageService.normalize("eng") == "en"
    assert LanguageService.normalize("tam-IN") == "ta"
    assert LanguageService.normalize("spa") == "es"
    assert LanguageService.normalize("hin") == "hi"


def test_normalized_provider_language_builds_explicit_reply_instruction():
    assert _language_instruction("eng") == ""
    assert "Spanish" in _language_instruction("spa")
    assert "Tamil" in _language_instruction("tam")
