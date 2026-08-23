from app.models import (
    Decision,
    IntentContract,
    TransactionProposal,
    VerificationResult,
    ViolationCode,
)


def verify_purchase(
    intent: IntentContract,
    transaction: TransactionProposal,
) -> VerificationResult:
    """
    Deterministically verifies a proposed purchase against
    a user-approved Intent Contract.

    This function never calls an AI model and never creates a payment.
    """

    violations: list[ViolationCode] = []
    questions: list[str] = []

    if transaction.currency != intent.currency:
        questions.append(
            f"Currency mismatch: user approved {intent.currency}, "
            f"but merchant offers {transaction.currency}."
        )

    if transaction.amount > intent.maximum_amount:
        violations.append(ViolationCode.AMOUNT_EXCEEDED)

    if not intent.subscription_allowed:
        if transaction.subscription_enabled is True:
            violations.append(ViolationCode.SUBSCRIPTION_PROHIBITED)
        elif transaction.subscription_enabled is None:
            questions.append("Is this a one-time purchase or a recurring subscription?")

    if intent.refundable_required:
        if transaction.refundable is False:
            violations.append(ViolationCode.REFUNDABILITY_REQUIRED)
        elif transaction.refundable is None:
            questions.append("Is the refund or return policy known?")

    transaction_features = {
        feature.strip().lower() for feature in transaction.features
    }

    missing_features = [
        feature
        for feature in intent.required_features
        if feature.strip().lower() not in transaction_features
    ]

    if missing_features:
        violations.append(ViolationCode.REQUIRED_FEATURE_MISSING)

    if intent.delivery_deadline is not None:
        if transaction.delivery_date is None:
            questions.append("What is the confirmed delivery date?")
        elif transaction.delivery_date > intent.delivery_deadline:
            violations.append(ViolationCode.DELIVERY_DEADLINE_MISSED)

    if violations:
        return VerificationResult(
            decision=Decision.BLOCK,
            violations=violations,
            clarification_questions=questions,
        )

    if questions:
        return VerificationResult(
            decision=Decision.ASK_USER,
            clarification_questions=questions,
        )

    return VerificationResult(decision=Decision.ALLOW)