from app.models import (
    IntentContract,
    IntentDraft,
    TransactionProposal,
)
from app.policy import verify_purchase


def test_rupees_normalized_to_inr():
    intent = IntentContract(
        product_type="headphones",
        maximum_amount=3000,
        currency="RUPEES",
    )

    assert intent.currency == "INR"


def test_rupee_symbol_normalized_to_inr():
    transaction = TransactionProposal(
        merchant="Demo Store",

        product_name="Headphones",
        amount=999,
        currency="₹",
    )

    assert transaction.currency == "INR"


def test_draft_currency_is_normalized():
    draft = IntentDraft(
        source_text="Buy headphones below 3000 rupees",
        currency="rupees",
    )

    assert draft.currency == "INR"


def test_equivalent_currencies_do_not_ask_question():
    intent = IntentContract(
        product_type="headphones",
        maximum_amount=3000,
        currency="RUPEES",
        subscription_allowed=True,
    )

    transaction = TransactionProposal(
        merchant="Demo Store",
        product_name="Headphones",
        amount=999,
        currency="₹",
        subscription_enabled=False,
        refundable=True,
    )

    result = verify_purchase(intent, transaction)

    assert not any(
        "currency mismatch" in question.lower()
        for question in result.clarification_questions
    )