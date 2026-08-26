from app.authorization import transaction_fingerprint
from app.merchant_analyzer import (
    analyze_merchant_text_safely,
)
from app.models import (
    Decision,
    IntentContract,
    TransactionProposal,
    ViolationCode,
)
from app.policy import verify_purchase


def subscription_intent(
    maximum_amount: float,
) -> IntentContract:
    return IntentContract(
        product_type="software",
        maximum_amount=maximum_amount,
        currency="INR",
        subscription_allowed=True,
    )


def test_trial_extracts_upfront_and_recurring_amounts():
    result = analyze_merchant_text_safely(
        "Seven-day trial for ₹49. A ₹499 subscription "
        "starts automatically after the trial.",
        provider="mock",
    )

    assert result.transaction is not None
    assert result.transaction.amount == 49
    assert result.transaction.subscription_enabled is True
    assert result.transaction.recurring_amount == 499
    assert result.transaction.billing_frequency == "after_trial"


def test_recurring_amount_over_budget_is_blocked():
    transaction = TransactionProposal(
        merchant="Demo Software",
        product_name="Trial Plan",
        amount=49,
        currency="INR",
        subscription_enabled=True,
        recurring_amount=499,
        billing_frequency="monthly",
    )

    result = verify_purchase(
        subscription_intent(maximum_amount=100),
        transaction,
    )

    assert result.decision == Decision.BLOCK
    assert (
        ViolationCode.RECURRING_AMOUNT_EXCEEDED
        in result.violations
    )


def test_recurring_amount_within_budget_is_allowed():
    transaction = TransactionProposal(
        merchant="Demo Software",
        product_name="Small Monthly Plan",
        amount=49,
        currency="INR",
        subscription_enabled=True,
        recurring_amount=99,
        billing_frequency="monthly",
    )

    result = verify_purchase(
        subscription_intent(maximum_amount=100),
        transaction,
    )

    assert result.decision == Decision.ALLOW


def test_unknown_recurring_amount_pauses_payment():
    transaction = TransactionProposal(
        merchant="Demo Software",
        product_name="Unclear Plan",
        amount=49,
        currency="INR",
        subscription_enabled=True,
        billing_frequency="monthly",
    )

    result = verify_purchase(
        subscription_intent(maximum_amount=100),
        transaction,
    )

    assert result.decision == Decision.ASK_USER
    assert any(
        "each renewal" in question.lower()
        for question in result.clarification_questions
    )


def test_authorization_fingerprint_binds_recurring_amount():
    first_transaction = TransactionProposal(
        merchant="Demo Software",
        product_name="Trial Plan",
        amount=49,
        currency="INR",
        subscription_enabled=True,
        recurring_amount=499,
        billing_frequency="monthly",
    )

    changed_transaction = first_transaction.model_copy(
        update={"recurring_amount": 999}
    )

    assert (
        transaction_fingerprint(first_transaction)
        != transaction_fingerprint(changed_transaction)
    )
