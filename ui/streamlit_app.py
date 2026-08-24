import sys
from datetime import date, timedelta
from pathlib import Path

import streamlit as st


# Make the project root importable when Streamlit runs this file.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.models import (  # noqa: E402
    Decision,
    IntentContract,
    TransactionProposal,
)
from app.policy import verify_purchase  # noqa: E402


# Browser-tab and page configuration.
st.set_page_config(
    page_title="IntentLock",
    page_icon="🔐",
    layout="wide",
)


# IntentLock visual design system.
st.markdown(
    """
    <style>
        .stApp {
            background-color: #F8FAFC;
            color: #021C29;
        }

        [data-testid="stHeader"] {
            background-color: rgba(248, 250, 252, 0.96);
            border-bottom: 1px solid #D0E0FF;
        }

        h1 {
            color: #0D1A48;
            letter-spacing: -0.04em;
            font-weight: 750;
        }

        h2,
        h3 {
            color: #192839;
            letter-spacing: -0.02em;
        }

        p,
        label {
            color: #203553;
        }

        [data-testid="stCaptionContainer"] {
            color: #768EA7;
        }

        div[data-baseweb="input"] {
            background-color: #FFFFFF;
            border-color: #D0E0FF;
            border-radius: 6px;
        }

        div[data-baseweb="input"]:focus-within {
            border-color: #4D7FFF;
            box-shadow: 0 0 0 2px rgba(77, 127, 255, 0.16);
        }

        div[data-baseweb="select"] > div {
            background-color: #FFFFFF;
            border-color: #D0E0FF;
            border-radius: 6px;
        }

        div.stButton > button {
            min-height: 46px;
            background-color: #2950DA;
            color: #FFFFFF;
            border: 1px solid #0D1A48;
            border-radius: 6px;
            box-shadow: none;
            font-weight: 650;
        }

        div.stButton > button:hover {
            background-color: #305EFF;
            color: #FFFFFF;
            border-color: #0D1A48;
        }

        div.stButton > button:focus {
            background-color: #2950DA;
            color: #FFFFFF;
            box-shadow: 0 0 0 3px rgba(77, 127, 255, 0.25);
        }

        .context-panel {
            margin: 12px 0 24px 0;
            padding: 14px 18px;
            background-color: #FFFFFF;
            color: #203553;
            border: 1px solid #D0E0FF;
            border-left: 4px solid #2950DA;
            border-radius: 6px;
        }

        .decision-card {
            margin: 12px 0;
            padding: 18px 20px;
            border: 1px solid;
            border-left-width: 6px;
            border-radius: 6px;
            font-weight: 650;
        }

        .decision-allow {
            background-color: #D0E0FF;
            color: #0D1A48;
            border-color: #2950DA;
        }

        .decision-block {
            background-color: #F0F4F6;
            color: #0B0A0D;
            border-color: #D52B1E;
        }

        .decision-ask {
            background-color: #FFFFFF;
            color: #203553;
            border-color: #768EA7;
        }

        [data-testid="stExpander"] {
            background-color: #FFFFFF;
            border: 1px solid #D0E0FF;
            border-radius: 6px;
        }

        code {
            background-color: #F0F4F6;
            color: #0B0A0D;
            border-radius: 3px;
        }

        a {
            color: #0000EE;
        }

        hr {
            border-color: #D0E0FF;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def parse_features(value: str) -> list[str]:
    """Convert comma-separated feature text into a clean list."""

    return [
        feature.strip()
        for feature in value.split(",")
        if feature.strip()
    ]


def parse_optional_boolean(value: str) -> bool | None:
    """Convert UI labels into True, False or unknown."""

    if value == "Yes":
        return True

    if value == "No":
        return False

    return None


# Page introduction.
st.title("IntentLock")

st.caption(
    "Semantic authorization gateway for AI-initiated purchases"
)

st.markdown(
    """
    <div class="context-panel">
        IntentLock verifies every AI-proposed purchase against rules
        explicitly approved by the human before payment is permitted.
    </div>
    """,
    unsafe_allow_html=True,
)


# Main input sections.
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


st.divider()


# Verify the proposed transaction.
if st.button(
    "Verify Purchase",
    type="primary",
    use_container_width=True,
):
    intent = IntentContract(
        product_type=product_type,
        maximum_amount=maximum_amount,
        required_features=parse_features(
            required_features_text
        ),
        subscription_allowed=subscription_allowed,
        refundable_required=refundable_required,
        delivery_deadline=delivery_deadline,
    )

    transaction = TransactionProposal(
        merchant=merchant,
        product_name=product_name,
        amount=transaction_amount,
        features=parse_features(
            transaction_features_text
        ),
        subscription_enabled=parse_optional_boolean(
            subscription_status
        ),
        refundable=parse_optional_boolean(
            refund_status
        ),
        delivery_date=proposed_delivery_date,
    )

    result = verify_purchase(
        intent,
        transaction,
    )

    st.subheader("3. IntentLock Decision")

    if result.decision == Decision.ALLOW:
        st.markdown(
            """
            <div class="decision-card decision-allow">
                ALLOW — Transaction satisfies the approved
                Intent Contract.
            </div>
            """,
            unsafe_allow_html=True,
        )

    elif result.decision == Decision.BLOCK:
        st.markdown(
            """
            <div class="decision-card decision-block">
                BLOCK — Transaction violates one or more
                approved rules.
            </div>
            """,
            unsafe_allow_html=True,
        )

    else:
        st.markdown(
            """
            <div class="decision-card decision-ask">
                ASK USER — More information is required
                before payment.
            </div>
            """,
            unsafe_allow_html=True,
        )

    if result.violations:
        st.write("**Confirmed violations:**")

        for violation in result.violations:
            st.write(f"- `{violation.value}`")

    if result.clarification_questions:
        st.write("**Required clarification:**")

        for question in result.clarification_questions:
            st.write(f"- {question}")

    with st.expander(
        "View structured verification result"
    ):
        st.json(
            result.model_dump(mode="json")
        )

    with st.expander(
        "View approved Intent Contract"
    ):
        st.json(
            intent.model_dump(mode="json")
        )

    with st.expander(
        "View proposed transaction"
    ):
        st.json(
            transaction.model_dump(mode="json")
        )