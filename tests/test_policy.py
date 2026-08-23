from datetime import date

from app.models import (
    Decision,
    IntentContract,
    TransactionProposal,
    ViolationCode,
)
from app.policy import verify_purchase


def base_intent() -> IntentContract:
    return IntentContract(
        product_type="headphones",
        maximum_amount=3000,
        required_features=["active noise cancellation"],
        subscription_allowed=False,
        refundable_required=True,
    )


def test_safe_purchase_is_allowed():
    transaction = TransactionProposal(
        merchant="Demo Electronics",
        product_name="SoundMax Pro",
        amount=2799,
        features=["active noise cancellation", "wireless"],
        subscription_enabled=False,
        refundable=True,
    )

    result = verify_purchase(base_intent(), transaction)

    assert result.decision == Decision.ALLOW
    assert result.violations == []


def test_hidden_subscription_is_blocked():
    transaction = TransactionProposal(
        merchant="Demo Electronics",
        product_name="SoundMax Pro + Premium Care",
        amount=2999,
        features=["active noise cancellation"],
        subscription_enabled=True,
        refundable=True,
    )

    result = verify_purchase(base_intent(), transaction)

    assert result.decision == Decision.BLOCK
    assert ViolationCode.SUBSCRIPTION_PROHIBITED in result.violations


def test_missing_refund_policy_asks_user():
    transaction = TransactionProposal(
        merchant="Unknown Store",
        product_name="SoundMax Lite",
        amount=2500,
        features=["active noise cancellation"],
        subscription_enabled=False,
        refundable=None,
    )

    result = verify_purchase(base_intent(), transaction)

    assert result.decision == Decision.ASK_USER
    assert "refund" in result.clarification_questions[0].lower()


def test_price_above_budget_is_blocked():
    transaction = TransactionProposal(
        merchant="Demo Electronics",
        product_name="Premium Headphones",
        amount=4500,
        features=["active noise cancellation"],
        subscription_enabled=False,
        refundable=True,
    )

    result = verify_purchase(base_intent(), transaction)

    assert result.decision == Decision.BLOCK
    assert ViolationCode.AMOUNT_EXCEEDED in result.violations


def test_late_delivery_is_blocked():
    intent = IntentContract(
        product_type="headphones",
        maximum_amount=3000,
        delivery_deadline=date(2026, 8, 25),
    )

    transaction = TransactionProposal(
        merchant="Demo Electronics",
        product_name="SoundMax Pro",
        amount=2799,
        subscription_enabled=False,
        refundable=True,
        delivery_date=date(2026, 8, 28),
    )

    result = verify_purchase(intent, transaction)

    assert result.decision == Decision.BLOCK
    assert ViolationCode.DELIVERY_DEADLINE_MISSED in result.violations