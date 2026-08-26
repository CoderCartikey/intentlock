from app.models import (
    Decision,
    IntentContract,
    TransactionProposal,
    VerificationResult,
    ViolationCode,
)


def _append_violation_once(
    violations: list[ViolationCode],
    violation: ViolationCode,
) -> None:
    if violation not in violations:
        violations.append(violation)


def verify_purchase(
    intent: IntentContract,
    transaction: TransactionProposal,
) -> VerificationResult:
    """
    Deterministically verify a purchase against a human-approved contract.

    This function never calls AI and never creates a payment.
    """

    violations: list[ViolationCode] = []
    questions: list[str] = []

    if transaction.currency != intent.currency:
        questions.append(
            f"Currency mismatch: user approved {intent.currency}, "
            f"but merchant offers {transaction.currency}."
        )

    if transaction.amount > intent.maximum_amount:
        _append_violation_once(
            violations,
            ViolationCode.AMOUNT_EXCEEDED,
        )

    if transaction.subscription_enabled is True:
        if not intent.subscription_allowed:
            _append_violation_once(
                violations,
                ViolationCode.SUBSCRIPTION_PROHIBITED,
            )
        else:
            if transaction.recurring_amount is None:
                questions.append(
                    "What amount will be charged on each renewal?"
                )
            elif (
                transaction.recurring_amount
                > intent.maximum_amount
            ):
                _append_violation_once(
                    violations,
                    ViolationCode.RECURRING_AMOUNT_EXCEEDED,
                )

            if not transaction.billing_frequency:
                questions.append(
                    "How often will the subscription renew?"
                )

    elif transaction.subscription_enabled is None:
        if not intent.subscription_allowed:
            questions.append(
                "Is this a one-time purchase or a recurring subscription?"
            )

    elif transaction.recurring_amount is not None:
        questions.append(
            "The merchant supplied a recurring amount but marked the "
            "purchase as non-subscription. Which term is correct?"
        )

    if intent.refundable_required:
        if transaction.refundable is False:
            _append_violation_once(
                violations,
                ViolationCode.REFUNDABILITY_REQUIRED,
            )
        elif transaction.refundable is None:
            questions.append(
                "Is the refund or return policy known?"
            )

    transaction_features = {
        feature.strip().lower()
        for feature in transaction.features
    }

    missing_features = [
        feature
        for feature in intent.required_features
        if feature.strip().lower() not in transaction_features
    ]

    if missing_features:
        _append_violation_once(
            violations,
            ViolationCode.REQUIRED_FEATURE_MISSING,
        )

    if intent.delivery_deadline is not None:
        if transaction.delivery_date is None:
            questions.append(
                "What is the confirmed delivery date?"
            )
        elif transaction.delivery_date > intent.delivery_deadline:
            _append_violation_once(
                violations,
                ViolationCode.DELIVERY_DEADLINE_MISSED,
            )

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

    return VerificationResult(
        decision=Decision.ALLOW
    )
