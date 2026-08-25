from pathlib import Path

from app.authorization import (
    create_payment_authorization,
)
from app.models import (
    Decision,
    TransactionProposal,
    VerificationResult,
)
from app.payment_executor import (
    PaymentExecutionError,
    PaymentExecutionStatus,
    execute_payment_authorization,
)


TEST_SECRET = (
    "intentlock-payment-test-secret-longer-than-32-characters"
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


def create_token(
    transaction: TransactionProposal,
) -> str:
    return create_payment_authorization(
        transaction=transaction,
        verification_result=VerificationResult(
            decision=Decision.ALLOW
        ),
        receipt_id="IL-PAYMENT-TEST",
        secret=TEST_SECRET,
    )


def test_valid_authorization_creates_mock_order(
    tmp_path: Path,
):
    transaction = safe_transaction()
    token = create_token(transaction)

    result = execute_payment_authorization(
        token=token,
        transaction=transaction,
        provider="mock",
        database_path=tmp_path / "payments.db",
        signing_secret=TEST_SECRET,
    )

    assert (
        result.status
        == PaymentExecutionStatus.ORDER_CREATED
    )
    assert result.order_id is not None
    assert result.order_id.startswith("order_mock_")


def test_authorization_can_only_be_used_once(
    tmp_path: Path,
):
    transaction = safe_transaction()
    token = create_token(transaction)
    database_path = tmp_path / "payments.db"

    first_result = execute_payment_authorization(
        token=token,
        transaction=transaction,
        provider="mock",
        database_path=database_path,
        signing_secret=TEST_SECRET,
    )

    second_result = execute_payment_authorization(
        token=token,
        transaction=transaction,
        provider="mock",
        database_path=database_path,
        signing_secret=TEST_SECRET,
    )

    assert (
        first_result.status
        == PaymentExecutionStatus.ORDER_CREATED
    )

    assert (
        second_result.status
        == PaymentExecutionStatus.DENIED
    )

    assert (
        second_result.error_code
        == PaymentExecutionError.TOKEN_ALREADY_USED
    )


def test_changed_amount_is_denied(
    tmp_path: Path,
):
    original_transaction = safe_transaction()
    token = create_token(original_transaction)

    changed_transaction = original_transaction.model_copy(
        update={"amount": 9999}
    )

    result = execute_payment_authorization(
        token=token,
        transaction=changed_transaction,
        provider="mock",
        database_path=tmp_path / "payments.db",
        signing_secret=TEST_SECRET,
    )

    assert (
        result.status
        == PaymentExecutionStatus.DENIED
    )

    assert (
        result.error_code
        == PaymentExecutionError.INVALID_AUTHORIZATION
    )

    assert (
        result.authorization_error
        == "TRANSACTION_MISMATCH"
    )


def test_invalid_token_is_denied(
    tmp_path: Path,
):
    result = execute_payment_authorization(
        token="not-a-valid-token",
        transaction=safe_transaction(),
        provider="mock",
        database_path=tmp_path / "payments.db",
        signing_secret=TEST_SECRET,
    )

    assert (
        result.status
        == PaymentExecutionStatus.DENIED
    )

    assert (
        result.error_code
        == PaymentExecutionError.INVALID_AUTHORIZATION
    )


def test_live_razorpay_key_is_prohibited(
    tmp_path: Path,
    monkeypatch,
):
    transaction = safe_transaction()
    token = create_token(transaction)

    monkeypatch.setenv(
        "RAZORPAY_KEY_ID",
        "rzp_live_this_must_never_be_used",
    )

    monkeypatch.setenv(
        "RAZORPAY_KEY_SECRET",
        "fake-live-secret",
    )

    result = execute_payment_authorization(
        token=token,
        transaction=transaction,
        provider="razorpay",
        database_path=tmp_path / "payments.db",
        signing_secret=TEST_SECRET,
    )

    assert (
        result.status
        == PaymentExecutionStatus.DENIED
    )

    assert (
        result.error_code
        == PaymentExecutionError.LIVE_KEY_PROHIBITED
    )


def test_razorpay_order_uses_exact_authorized_amount(
    tmp_path: Path,
    monkeypatch,
):
    transaction = safe_transaction()
    token = create_token(transaction)
    captured_request = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "id": "order_test_intentlock",
                "status": "created",
            }

    def fake_post(
        url,
        auth,
        json,
        timeout,
    ):
        captured_request["url"] = url
        captured_request["auth"] = auth
        captured_request["json"] = json
        captured_request["timeout"] = timeout

        return FakeResponse()

    monkeypatch.setenv(
        "RAZORPAY_KEY_ID",
        "rzp_test_intentlock",
    )

    monkeypatch.setenv(
        "RAZORPAY_KEY_SECRET",
        "fake-test-secret",
    )

    monkeypatch.setattr(
        "app.payment_executor.httpx.post",
        fake_post,
    )

    result = execute_payment_authorization(
        token=token,
        transaction=transaction,
        provider="razorpay",
        database_path=tmp_path / "payments.db",
        signing_secret=TEST_SECRET,
    )

    assert (
        result.status
        == PaymentExecutionStatus.ORDER_CREATED
    )

    assert result.order_id == "order_test_intentlock"

    assert (
        captured_request["url"]
        == "https://api.razorpay.com/v1/orders"
    )

    assert captured_request["json"]["amount"] == 299900
    assert captured_request["json"]["currency"] == "INR"
    assert (
        captured_request["json"]["partial_payment"]
        is False
    )