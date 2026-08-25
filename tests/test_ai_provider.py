import app.ai_provider as ai_provider
from app.models import (
    ExtractionStatus,
    IntentDraft,
)


USER_REQUEST = (
    "Buy headphones below 3000 rupees. "
    "They must have active noise cancellation, "
    "must be refundable, and must not include "
    "a subscription."
)


def test_mock_extraction_understands_basic_intent():
    result = ai_provider.extract_intent_safely(
        USER_REQUEST,
        provider_name="mock",
    )

    assert result.status == ExtractionStatus.FALLBACK
    assert result.draft is not None
    assert result.draft.product_type == "headphones"
    assert result.draft.maximum_amount == 3000
    assert result.draft.currency == "INR"
    assert (
        "active noise cancellation"
        in result.draft.required_features
    )
    assert result.draft.subscription_allowed is False
    assert result.draft.refundable_required is True


def test_missing_groq_key_uses_fallback(monkeypatch):
    monkeypatch.delenv(
        "GROQ_API_KEY",
        raising=False,
    )

    result = ai_provider.extract_intent_safely(
        USER_REQUEST,
        provider_name="groq",
    )

    assert result.status == ExtractionStatus.FALLBACK
    assert result.provider == "mock"
    assert result.draft is not None
    assert result.error_code == "MISSING_GROQ_API_KEY"


def test_successful_groq_result_is_accepted(
    monkeypatch,
):
    monkeypatch.setenv(
        "GROQ_API_KEY",
        "fake-test-key",
    )

    expected_draft = IntentDraft(
        source_text=USER_REQUEST,
        product_type="headphones",
        maximum_amount=3000,
        currency="INR",
        required_features=[
            "active noise cancellation"
        ],
        subscription_allowed=False,
        refundable_required=True,
    )

    def fake_groq_extraction(
        user_text: str,
    ) -> IntentDraft:
        assert user_text == USER_REQUEST
        return expected_draft

    monkeypatch.setattr(
        ai_provider,
        "extract_intent_with_groq",
        fake_groq_extraction,
    )

    result = ai_provider.extract_intent_safely(
        USER_REQUEST,
        provider_name="groq",
    )

    assert result.status == ExtractionStatus.SUCCESS
    assert result.provider == "groq"
    assert result.draft == expected_draft


def test_groq_timeout_uses_safe_fallback(
    monkeypatch,
):
    monkeypatch.setenv(
        "GROQ_API_KEY",
        "fake-test-key",
    )

    def failed_groq_extraction(
        user_text: str,
    ) -> IntentDraft:
        raise TimeoutError("Simulated timeout")

    monkeypatch.setattr(
        ai_provider,
        "extract_intent_with_groq",
        failed_groq_extraction,
    )

    result = ai_provider.extract_intent_safely(
        USER_REQUEST,
        provider_name="groq",
    )

    assert result.status == ExtractionStatus.FALLBACK
    assert result.provider == "mock"
    assert result.draft is not None
    assert result.error_code == "TimeoutError"


def test_empty_request_fails_closed():
    result = ai_provider.extract_intent_safely(
        "   ",
        provider_name="groq",
    )

    assert result.status == ExtractionStatus.FAILED
    assert result.draft is None
    assert result.error_code == "EMPTY_USER_TEXT"