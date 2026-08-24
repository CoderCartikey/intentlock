import sys
from datetime import date, timedelta
from pathlib import Path

import streamlit as st


# Allow Streamlit to import the app package from the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.models import (  # noqa: E402
    Decision,
    IntentContract,
    TransactionProposal,
)
from app.policy import verify_purchase  # noqa: E402


st.set_page_config(
    page_title="IntentLock",
    page_icon="🔐",
    layout="wide",
)

st.title("IntentLock")
st.caption(
    "Semantic authorization gateway for AI-initiated purchases"
)

st.info(
    "IntentLock verifies a proposed purchase against rules approved "
    "by the human before allowing payment."
)


intent_column, transaction_column = st.columns(2)


with intent_column:
    st.subheader("1. User Intent Contract")

    product_type = st.text_input(
        "Product type",
        value="headphones",
    )

    maximum_amount = st.number_input(
        "Maximum approved amount (₹)",
        min_value=1.0,
        value=3000.0,
        step=100.0,
    )

    required_features_text = st.text_input(
        "Required features, separated by commas",
        value="active noise cancellation",
    )

    subscription_allowed = st.checkbox(
        "Subscription allowed",
        value=False,
    )

    refundable_required = st.checkbox(
        "Product must be refundable",
        value=True,
    )

    use_delivery_deadline = st.checkbox(
        "Require delivery before a deadline",
        value=False,
    )

    delivery_deadline = None

    if use_delivery_deadline:
        delivery_deadline = st.date_input(
            "Delivery deadline",
            value=date.today() + timedelta(days=3),
        )


with transaction_column:
    st.subheader("2. Proposed Transaction")

    merchant = st.text_input(
        "Merchant",
        value="Demo Electronics",
    )

    product_name = st.text_input(
        "Product name",
        value="SoundMax Pro",
    )

    transaction_amount = st.number_input(
        "Transaction amount (₹)",
        min_value=1.0,
        value=2999.0,
        step=100.0,
    )

    transaction_features_text = st.text_input(
        "Product features, separated by commas",
        value="active noise cancellation, wireless",
    )

    subscription_status = st.selectbox(
        "Subscription status",
        options=["No", "Yes", "Unknown"],
    )

    refund_status = st.selectbox(
        "Refundability",
        options=["Yes", "No", "Unknown"],
    )

    delivery_date_known = st.checkbox(
        "Delivery date is known",
        value=False,
    )

    proposed_delivery_date = None

    if delivery_date_known:
        proposed_delivery_date = st.date_input(
            "Proposed delivery date",
            value=date.today() + timedelta(days=2),
        )


def parse_features(value: str) -> list[str]:
    return [
        feature.strip()
        for feature in value.split(",")
        if feature.strip()
    ]


def parse_optional_boolean(value: str) -> bool | None:
    if value == "Yes":
        return True

    if value == "No":
        return False

    return None


st.divider()


if st.button(
    "Verify Purchase",
    type="primary",
    use_container_width=True,
):
    intent = IntentContract(
        product_type=product_type,
        maximum_amount=maximum_amount,
        required_features=parse_features(required_features_text),
        subscription_allowed=subscription_allowed,
        refundable_required=refundable_required,
        delivery_deadline=delivery_deadline,
    )

    transaction = TransactionProposal(
        merchant=merchant,
        product_name=product_name,
        amount=transaction_amount,
        features=parse_features(transaction_features_text),
        subscription_enabled=parse_optional_boolean(
            subscription_status
        ),
        refundable=parse_optional_boolean(refund_status),
        delivery_date=proposed_delivery_date,
    )

    result = verify_purchase(intent, transaction)

    st.subheader("3. IntentLock Decision")

    if result.decision == Decision.ALLOW:
        st.success(
            "ALLOW — This transaction satisfies the approved Intent Contract."
        )

    elif result.decision == Decision.BLOCK:
        st.error(
            "BLOCK — This transaction violates one or more approved rules."
        )

    else:
        st.warning(
            "ASK USER — IntentLock requires more information before payment."
        )

    if result.violations:
        st.write("**Confirmed violations:**")

        for violation in result.violations:
            st.write(f"- `{violation.value}`")

    if result.clarification_questions:
        st.write("**Required clarification:**")

        for question in result.clarification_questions:
            st.write(f"- {question}")

    with st.expander("View structured verification result"):
        st.json(result.model_dump(mode="json"))

    with st.expander("View approved Intent Contract"):
        st.json(intent.model_dump(mode="json"))

    with st.expander("View proposed transaction"):
        st.json(transaction.model_dump(mode="json"))