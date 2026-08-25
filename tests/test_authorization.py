from datetime import datetime, timedelta, timezone

import pytest

from app.authorization import (
    AuthorizationError,
    create_payment_authorization,
    transaction_fingerprint,
    verify_payment_authorization,
)
from app.models import (
    Decision,
    TransactionProposal,
    VerificationResult,
)


TEST_SECRET = (
    "intentlock-test-secret-that-is-longer-than-32-characters"
)


def safe_transaction() -> TransactionProposal:
    return TransactionProposal(
        merchant="Demo Electronics",
        product_name="SoundMax Pro",
        amount=2999,
        currency="INR",
        features=[
            "active noise cancellation",
            "wireless",
        ],
        subscription_enabled=False,
        refundable=True,
    )


def allowed_result() -> VerificationResult:
    return VerificationResult(
        decision=Decision.ALLOW,
    )


def test_allowed_transaction_gets_valid_authorization():
    transaction = safe_transaction()

    token = create_payment_authorization(
        transaction=transaction,
        verification_result=allowed_result(),
        receipt_id="IL-TEST-001",
        secret=TEST_SECRET,
    )

    result = verify_payment_authorization(
        token=token,
        transaction=transaction,
        secret=TEST_SECRET,
    )

    assert result.valid is True
    assert result.error_code is None
    assert result.payload is not None
    assert result.payload.receipt_id == "IL-TEST-001"


def test_blocked_transaction_cannot_get_authorization():
    transaction = safe_transaction()

    blocked_result = VerificationResult(
        decision=Decision.BLOCK,
    )

    with pytest.raises(ValueError):
        create_payment_authorization(
            transaction=transaction,
            verification_result=blocked_result,
            receipt_id="IL-TEST-002",
            secret=TEST_SECRET,
        )


def test_ask_user_transaction_cannot_get_authorization():
    transaction = safe_transaction()

    ask_user_result = VerificationResult(
        decision=Decision.ASK_USER,
    )

    with pytest.raises(ValueError):
        create_payment_authorization(
            transaction=transaction,
            verification_result=ask_user_result,
            receipt_id="IL-TEST-003",
            secret=TEST_SECRET,
        )


def test_amount_change_invalidates_authorization():
    original_transaction = safe_transaction()

    token = create_payment_authorization(
        transaction=original_transaction,
        verification_result=allowed_result(),
        receipt_id="IL-TEST-004",
        secret=TEST_SECRET,
    )

    changed_transaction = original_transaction.model_copy(
        update={
            "amount": 9999,
        }
    )

    result = verify_payment_authorization(
        token=token,
        transaction=changed_transaction,
        secret=TEST_SECRET,
    )

    assert result.valid is False
    assert (
        result.error_code
        == AuthorizationError.TRANSACTION_MISMATCH
    )


def test_tampered_signature_is_rejected():
    transaction = safe_transaction()

    token = create_payment_authorization(
        transaction=transaction,
        verification_result=allowed_result(),
        receipt_id="IL-TEST-005",
        secret=TEST_SECRET,
    )

    encoded_payload, encoded_signature = token.split(".")

    replacement = (
        "A"
        if encoded_signature[0] != "A"
        else "B"
    )

    tampered_signature = (
        replacement + encoded_signature[1:]
    )

    tampered_token = (
        f"{encoded_payload}.{tampered_signature}"
    )

    result = verify_payment_authorization(
        token=tampered_token,
        transaction=transaction,
        secret=TEST_SECRET,
    )

    assert result.valid is False
    assert (
        result.error_code
        == AuthorizationError.INVALID_SIGNATURE
    )


def test_expired_authorization_is_rejected():
    transaction = safe_transaction()

    issued_at = datetime(
        2026,
        8,
        25,
        12,
        0,
        tzinfo=timezone.utc,
    )

    token = create_payment_authorization(
        transaction=transaction,
        verification_result=allowed_result(),
        receipt_id="IL-TEST-006",
        expires_in_seconds=60,
        secret=TEST_SECRET,
        now=issued_at,
    )

    result = verify_payment_authorization(
        token=token,
        transaction=transaction,
        secret=TEST_SECRET,
        now=issued_at + timedelta(seconds=61),
    )

    assert result.valid is False
    assert (
        result.error_code
        == AuthorizationError.EXPIRED_TOKEN
    )


def test_transaction_fingerprint_is_stable():
    first_transaction = safe_transaction()
    second_transaction = safe_transaction()

    assert (
        transaction_fingerprint(first_transaction)
        == transaction_fingerprint(second_transaction)
    )