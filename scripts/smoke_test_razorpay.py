from app.authorization import (
    create_payment_authorization,
)
from app.audit import record_verification
from app.models import (
    Decision,
    IntentContract,
    TransactionProposal,
)
from app.payment_executor import (
    PaymentExecutionStatus,
    execute_payment_authorization,
)
from app.policy import verify_purchase


intent = IntentContract(
    product_type="headphones",
    maximum_amount=3000,
    currency="INR",
    required_features=[
        "active noise cancellation",
    ],
    subscription_allowed=False,
    refundable_required=True,
)


transaction = TransactionProposal(
    merchant="IntentLock Test Merchant",
    product_name="SoundMax Pro Headphones",
    amount=99,
    currency="INR",
    features=[
        "active noise cancellation",
        "wireless",
    ],
    subscription_enabled=False,
    refundable=True,
)


verification_result = verify_purchase(
    intent,
    transaction,
)


print("\n1. POLICY DECISION")
print("=" * 50)
print(verification_result.model_dump_json(indent=2))


if verification_result.decision != Decision.ALLOW:
    raise RuntimeError(
        "Smoke-test transaction was not allowed"
    )


receipt_id = record_verification(
    intent,
    transaction,
    verification_result,
)


print("\n2. AUDIT RECEIPT")
print("=" * 50)
print(receipt_id)


authorization_token = create_payment_authorization(
    transaction=transaction,
    verification_result=verification_result,
    receipt_id=receipt_id,
)


print("\n3. SIGNED AUTHORIZATION")
print("=" * 50)
print(
    "Authorization created successfully. "
    "The secret token is intentionally not displayed."
)


execution_result = execute_payment_authorization(
    token=authorization_token,
    transaction=transaction,
    provider="razorpay",
)


print("\n4. RAZORPAY TEST ORDER")
print("=" * 50)
print(execution_result.model_dump_json(indent=2))


if (
    execution_result.status
    == PaymentExecutionStatus.ORDER_CREATED
):
    print("\nRAZORPAY TEST ORDER CREATED SUCCESSFULLY")
    print(f"Order ID: {execution_result.order_id}")

else:
    print("\nRAZORPAY TEST ORDER WAS NOT CREATED")
    print(f"Reason: {execution_result.error_code}")