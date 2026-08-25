import sys
from datetime import date, timedelta
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.ai_provider import extract_intent_safely  # noqa: E402
from app.audit import get_recent_records, record_verification  # noqa: E402
from app.models import (  # noqa: E402
    Decision,
    ExtractionStatus,
    IntentContract,
    TransactionProposal,
    VerificationResult,
)
from app.policy import verify_purchase  # noqa: E402


st.set_page_config(
    page_title="IntentLock",
    page_icon="🔐",
    layout="wide",
)


# Compact, utility-style interface.
st.markdown(
    """
    <style>
        .stApp {
            background: #F0F4F6;
            color: #021C29;
        }

        h1, h2, h3 {
            color: #0D1A48;
        }

        div[data-baseweb="input"],
        div[data-baseweb="select"] > div,
        [data-testid="stExpander"] {
            background: #FFFFFF;
            border-color: #768EA7;
            border-radius: 2px;
        }

        div.stButton > button,
        div[data-testid="stFormSubmitButton"] > button {
            background: #2950DA;
            color: #FFFFFF;
            border: 1px solid #0D1A48;
            border-radius: 2px;
            box-shadow: none;
            font-weight: 600;
        }

        div.stButton > button:hover,
        div[data-testid="stFormSubmitButton"] > button:hover {
            background: #305EFF;
            color: #FFFFFF;
        }

        .status-box {
            padding: 14px;
            margin: 10px 0;
            background: #FFFFFF;
            border: 1px solid #8794A7;
            border-left-width: 6px;
            border-radius: 2px;
        }

        .status-allow {
            border-left-color: #2950DA;
            color: #0D1A48;
        }

        .status-block {
            border-left-color: #D52B1E;
            color: #0B0A0D;
        }

        .status-ask {
            border-left-color: #768EA7;
            color: #203553;
        }

        code {
            color: #0B0A0D;
            background: #FFFFFF;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def initialize_state() -> None:
    defaults = {
        "purchase_request": (
            "Buy headphones below 3000 rupees. "
            "They must have active noise cancellation, "
            "must be refundable, and must not include "
            "a subscription."
        ),
        "intent_product_type": "headphones",
        "intent_maximum_amount": 3000.0,
        "intent_currency": "INR",
        "intent_required_features": (
            "active noise cancellation"
        ),
        "intent_subscription_policy": "Prohibited",
        "intent_refund_policy": "Required",
        "intent_delivery_enabled": False,
        "intent_delivery_deadline": (
            date.today() + timedelta(days=3)
        ),
        "approved_intent": None,
        "extraction_result": None,
        "latest_verification": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def features_from_text(value: str) -> list[str]:
    return [
        feature.strip()
        for feature in value.split(",")
        if feature.strip()
    ]


def optional_boolean(value: str) -> bool | None:
    if value == "Yes":
        return True

    if value == "No":
        return False

    return None


def apply_draft_to_form() -> None:
    extraction = st.session_state.extraction_result

    if extraction is None or extraction.draft is None:
        return

    draft = extraction.draft

    st.session_state.intent_product_type = (
        draft.product_type or ""
    )

    st.session_state.intent_maximum_amount = (
        draft.maximum_amount or 0.0
    )

    st.session_state.intent_currency = (
        draft.currency or ""
    )

    st.session_state.intent_required_features = ", ".join(
        draft.required_features
    )

    if draft.subscription_allowed is True:
        st.session_state.intent_subscription_policy = "Allowed"
    elif draft.subscription_allowed is False:
        st.session_state.intent_subscription_policy = "Prohibited"
    else:
        st.session_state.intent_subscription_policy = "Unspecified"

    if draft.refundable_required is True:
        st.session_state.intent_refund_policy = "Required"
    elif draft.refundable_required is False:
        st.session_state.intent_refund_policy = "Not required"
    else:
        st.session_state.intent_refund_policy = "Unspecified"

    st.session_state.intent_delivery_enabled = (
        draft.delivery_deadline is not None
    )

    if draft.delivery_deadline is not None:
        st.session_state.intent_delivery_deadline = (
            draft.delivery_deadline
        )

    # Every new draft invalidates the previously approved contract.
    st.session_state.approved_intent = None


initialize_state()


st.title("IntentLock")
st.caption(
    "Human-authorized transaction control for AI commerce"
)


# -------------------------------------------------------------------
# Stage 1: AI extraction
# -------------------------------------------------------------------

st.header("1. Describe the purchase")

st.text_area(
    "Natural-language purchasing instruction",
    key="purchase_request",
    height=110,
)

if st.button(
    "Extract Intent Draft",
    use_container_width=True,
):
    extraction_result = extract_intent_safely(
        st.session_state.purchase_request
    )

    st.session_state.extraction_result = (
        extraction_result
    )

    apply_draft_to_form()
    st.rerun()


extraction = st.session_state.extraction_result

if extraction is not None:
    if extraction.status == ExtractionStatus.SUCCESS:
        st.success(
            f"Live AI extraction succeeded using "
            f"{extraction.provider}: {extraction.model}"
        )

    elif extraction.status == ExtractionStatus.FALLBACK:
        st.warning(
            "AI was unavailable or mock mode was selected. "
            "A conservative fallback draft was created. "
            "Manual review is mandatory."
        )

        if extraction.error_code:
            st.caption(
                f"Fallback reason: {extraction.error_code}"
            )

    else:
        st.error(
            "Intent extraction failed. No contract was created."
        )

    if extraction.draft is not None:
        if extraction.draft.ambiguities:
            st.write("**Detected ambiguities:**")

            for ambiguity in extraction.draft.ambiguities:
                st.write(f"- {ambiguity}")

        with st.expander("View unapproved Intent Draft"):
            st.json(
                extraction.draft.model_dump(mode="json")
            )


# -------------------------------------------------------------------
# Stage 2: Human review and approval
# -------------------------------------------------------------------

st.header("2. Review and approve the Intent Contract")

with st.form("intent_approval_form"):
    left, right = st.columns(2)

    with left:
        st.text_input(
            "Product type",
            key="intent_product_type",
        )

        st.number_input(
            "Maximum amount",
            min_value=0.0,
            step=100.0,
            key="intent_maximum_amount",
        )

        st.text_input(
            "Currency",
            key="intent_currency",
        )

        st.text_input(
            "Required features, comma-separated",
            key="intent_required_features",
        )

    with right:
        st.selectbox(
            "Subscription policy",
            options=[
                "Unspecified",
                "Prohibited",
                "Allowed",
            ],
            key="intent_subscription_policy",
        )

        st.selectbox(
            "Refund policy",
            options=[
                "Unspecified",
                "Required",
                "Not required",
            ],
            key="intent_refund_policy",
        )

        st.checkbox(
            "Use a delivery deadline",
            key="intent_delivery_enabled",
        )

        if st.session_state.intent_delivery_enabled:
            st.date_input(
                "Delivery deadline",
                key="intent_delivery_deadline",
            )

    approve_contract = st.form_submit_button(
        "Approve Intent Contract",
        use_container_width=True,
    )


if approve_contract:
    approval_errors = []

    if not st.session_state.intent_product_type.strip():
        approval_errors.append(
            "Product type is required."
        )

    if st.session_state.intent_maximum_amount <= 0:
        approval_errors.append(
            "Maximum amount must be greater than zero."
        )

    if not st.session_state.intent_currency.strip():
        approval_errors.append(
            "Currency is required."
        )

    if (
        st.session_state.intent_subscription_policy
        == "Unspecified"
    ):
        approval_errors.append(
            "Choose an explicit subscription policy."
        )

    if (
        st.session_state.intent_refund_policy
        == "Unspecified"
    ):
        approval_errors.append(
            "Choose an explicit refund policy."
        )

    if approval_errors:
        for error in approval_errors:
            st.error(error)

    else:
        approved_contract = IntentContract(
            product_type=(
                st.session_state.intent_product_type.strip()
            ),
            maximum_amount=(
                st.session_state.intent_maximum_amount
            ),
            currency=(
                st.session_state.intent_currency.strip().upper()
            ),
            required_features=features_from_text(
                st.session_state.intent_required_features
            ),
            subscription_allowed=(
                st.session_state.intent_subscription_policy
                == "Allowed"
            ),
            refundable_required=(
                st.session_state.intent_refund_policy
                == "Required"
            ),
            delivery_deadline=(
                st.session_state.intent_delivery_deadline
                if st.session_state.intent_delivery_enabled
                else None
            ),
        )

        st.session_state.approved_intent = (
            approved_contract.model_dump(mode="json")
        )

        st.success(
            "Intent Contract approved by the human."
        )


if st.session_state.approved_intent is not None:
    with st.expander("View approved Intent Contract"):
        st.json(st.session_state.approved_intent)
else:
    st.info(
        "No approved Intent Contract exists yet. "
        "AI drafts cannot authorize transactions."
    )


# -------------------------------------------------------------------
# Stage 3: Proposed transaction
# -------------------------------------------------------------------

st.header("3. Enter the proposed transaction")

with st.form("transaction_form"):
    transaction_left, transaction_right = st.columns(2)

    with transaction_left:
        merchant = st.text_input(
            "Merchant",
            value="Demo Electronics",
        )

        product_name = st.text_input(
            "Product name",
            value="SoundMax Pro",
        )

        transaction_amount = st.number_input(
            "Transaction amount",
            min_value=1.0,
            value=2999.0,
            step=100.0,
        )

        transaction_currency = st.text_input(
            "Transaction currency",
            value="INR",
        )

    with transaction_right:
        transaction_features_text = st.text_input(
            "Product features, comma-separated",
            value=(
                "active noise cancellation, wireless"
            ),
        )

        subscription_status = st.selectbox(
            "Does this transaction create a subscription?",
            options=[
                "No",
                "Yes",
                "Unknown",
            ],
        )

        refundable_status = st.selectbox(
            "Is the purchase refundable?",
            options=[
                "Yes",
                "No",
                "Unknown",
            ],
        )

        delivery_known = st.checkbox(
            "Delivery date is known",
            value=False,
        )

        transaction_delivery_date = None

        if delivery_known:
            transaction_delivery_date = st.date_input(
                "Proposed delivery date",
                value=date.today() + timedelta(days=2),
            )

    verify_transaction = st.form_submit_button(
        "Verify Proposed Transaction",
        use_container_width=True,
    )


if verify_transaction:
    if st.session_state.approved_intent is None:
        st.error(
            "Transaction cannot be verified because no "
            "human-approved Intent Contract exists."
        )

    else:
        intent = IntentContract.model_validate(
            st.session_state.approved_intent
        )

        transaction = TransactionProposal(
            merchant=merchant,
            product_name=product_name,
            amount=transaction_amount,
            currency=transaction_currency.strip().upper(),
            features=features_from_text(
                transaction_features_text
            ),
            subscription_enabled=optional_boolean(
                subscription_status
            ),
            refundable=optional_boolean(
                refundable_status
            ),
            delivery_date=transaction_delivery_date,
        )

        result = verify_purchase(
            intent,
            transaction,
        )

        receipt_id = record_verification(
            intent,
            transaction,
            result,
        )

        st.session_state.latest_verification = {
            "receipt_id": receipt_id,
            "intent": intent.model_dump(mode="json"),
            "transaction": transaction.model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
        }


# -------------------------------------------------------------------
# Stage 4: Decision and receipt
# -------------------------------------------------------------------

latest = st.session_state.latest_verification

if latest is not None:
    result = VerificationResult.model_validate(
        latest["result"]
    )

    st.header("4. Decision")

    if result.decision == Decision.ALLOW:
        st.markdown(
            """
            <div class="status-box status-allow">
                <strong>ALLOW</strong><br>
                The proposed transaction satisfies the
                human-approved Intent Contract.
            </div>
            """,
            unsafe_allow_html=True,
        )

    elif result.decision == Decision.BLOCK:
        st.markdown(
            """
            <div class="status-box status-block">
                <strong>BLOCK</strong><br>
                The proposed transaction violates one or more
                approved constraints.
            </div>
            """,
            unsafe_allow_html=True,
        )

    else:
        st.markdown(
            """
            <div class="status-box status-ask">
                <strong>ASK USER</strong><br>
                Information is missing or ambiguous.
                No payment should be created.
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write(
        f"**Audit receipt:** `{latest['receipt_id']}`"
    )

    if result.violations:
        st.write("**Violations:**")

        for violation in result.violations:
            st.write(f"- `{violation.value}`")

    if result.clarification_questions:
        st.write("**Clarification required:**")

        for question in result.clarification_questions:
            st.write(f"- {question}")

    with st.expander("View complete decision receipt"):
        st.json(latest)


# -------------------------------------------------------------------
# Stage 5: Audit history
# -------------------------------------------------------------------

st.header("5. Audit history")

records = get_recent_records(limit=10)

if records:
    audit_rows = []

    for record in records:
        audit_rows.append(
            {
                "Receipt": record["receipt_id"],
                "Time (UTC)": (
                    record["created_at"][:19]
                    .replace("T", " ")
                ),
                "Decision": record["decision"],
                "Merchant": (
                    record["transaction"]["merchant"]
                ),
                "Product": (
                    record["transaction"]["product_name"]
                ),
                "Amount": (
                    record["transaction"]["amount"]
                ),
                "Currency": (
                    record["transaction"]["currency"]
                ),
            }
        )

    st.dataframe(
        audit_rows,
        use_container_width=True,
        hide_index=True,
    )

else:
    st.caption(
        "No verification records have been created yet."
    )