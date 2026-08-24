from app.audit import get_recent_records, record_verification
from app.models import (
    Decision,
    IntentContract,
    TransactionProposal,
)
from app.policy import verify_purchase


def build_intent() -> IntentContract:
    return IntentContract(
        product_type="headphones",
        maximum_amount=3000,
        required_features=["active noise cancellation"],
        subscription_allowed=False,
        refundable_required=True,
    )


def test_allowed_decision_is_recorded(tmp_path):
    database_path = tmp_path / "test_intentlock.db"

    intent = build_intent()

    transaction = TransactionProposal(
        merchant="Demo Electronics",
        product_name="SoundMax Pro",
        amount=2799,
        features=["active noise cancellation"],
        subscription_enabled=False,
        refundable=True,
    )

    result = verify_purchase(intent, transaction)

    receipt_id = record_verification(
        intent,
        transaction,
        result,
        db_path=database_path,
    )

    records = get_recent_records(
        db_path=database_path,
    )

    assert receipt_id.startswith("IL-")
    assert len(records) == 1
    assert records[0]["receipt_id"] == receipt_id
    assert records[0]["decision"] == Decision.ALLOW.value
    assert records[0]["transaction"]["amount"] == 2799


def test_blocked_decision_is_recorded(tmp_path):
    database_path = tmp_path / "test_intentlock.db"

    intent = build_intent()

    transaction = TransactionProposal(
        merchant="Demo Electronics",
        product_name="Premium Subscription Headphones",
        amount=2999,
        features=["active noise cancellation"],
        subscription_enabled=True,
        refundable=True,
    )

    result = verify_purchase(intent, transaction)

    receipt_id = record_verification(
        intent,
        transaction,
        result,
        db_path=database_path,
    )

    records = get_recent_records(
        db_path=database_path,
    )

    assert len(records) == 1
    assert records[0]["receipt_id"] == receipt_id
    assert records[0]["decision"] == Decision.BLOCK.value
    assert (
        "SUBSCRIPTION_PROHIBITED"
        in records[0]["result"]["violations"]
    )