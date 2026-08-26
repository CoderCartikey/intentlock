# IntentLock Architecture

## Design thesis

IntentLock separates **language understanding** from **financial authority**. Models may propose structured facts, but only human-confirmed constraints and deterministic code can authorize a Razorpay Test Mode order.

## End-to-end flow

```mermaid
sequenceDiagram
    actor User
    participant UI as Streamlit UI
    participant IA as Intent AI
    participant MA as Merchant AI
    participant SO as Safety Overlay
    participant PE as Policy Engine
    participant AU as Authorization Service
    participant EX as Payment Executor
    participant RP as Razorpay Test Mode
    participant DB as SQLite Audit

    User->>UI: Describe desired purchase
    UI->>IA: Extract draft constraints
    IA-->>UI: Unapproved IntentDraft
    User->>UI: Review and confirm rules

    User->>UI: Submit merchant text
    UI->>MA: Extract merchant facts
    UI->>SO: Scan untrusted text
    MA-->>SO: Proposed structured facts
    SO-->>UI: Corrected facts + evidence + injection warnings

    UI->>PE: Verify facts against approved contract
    PE->>DB: Store decision receipt

    alt BLOCK
        PE-->>UI: Violations; no authorization
    else ASK_USER
        PE-->>UI: Clarification questions; no authorization
    else ALLOW
        PE->>AU: Create signed authorization
        AU-->>UI: Short-lived token bound to exact transaction
        UI->>EX: Execute token with transaction
        EX->>EX: Verify signature, expiry, fingerprint and one-time use
        EX->>RP: Create Test Mode order
        RP-->>EX: Order ID
        EX-->>UI: ORDER_CREATED
    end
```

## Trust boundaries

### Untrusted

- User natural-language text before review
- Merchant/product/checkout text
- AI model output
- Browser-side values submitted after approval

### Trusted only after validation

- Pydantic models
- Human-confirmed `IntentContract`
- Deterministic policy result
- HMAC-verified transaction authorization
- Razorpay Test Mode API response

## Core components

### Intent extraction

`app/ai_provider.py` converts natural language into an `IntentDraft`. The draft cannot authorize payment. The user must review and confirm it as an `IntentContract`.

### Merchant analysis

`app/merchant_analyzer.py` treats merchant text as data, detects prompt-injection phrases, asks the model for strict structured output, and applies deterministic corrections when explicit recurring or non-refundable wording contradicts the model.

### Recurring-price representation

`TransactionProposal.amount` represents the immediate checkout charge. `recurring_amount` represents the future renewal charge, and `billing_frequency` records its cadence or known activation timing. This prevents a ₹49 trial from hiding a ₹499 renewal.

### Policy engine

`app/policy.py` contains no AI calls and no payment calls. It compares a transaction with the approved contract and returns exactly one decision:

- `ALLOW`: all required facts are known and rules pass.
- `BLOCK`: at least one confirmed rule is violated.
- `ASK_USER`: a decision-critical fact is missing or contradictory.

### Audit trail

`app/audit.py` stores the contract, transaction, decision, violations, clarification questions, timestamp and receipt ID in SQLite.

### Authorization

`app/authorization.py` creates an HMAC-SHA256 token only after `ALLOW`. The token contains an expiry, receipt ID and fingerprint of the complete transaction—including recurring terms.

### Payment executor

`app/payment_executor.py` verifies the signature, expiry, exact transaction and one-time use before calling Razorpay's Orders API. Live Razorpay keys are rejected.

## Failure behaviour

| Failure | Behaviour |
|---|---|
| AI timeout, rate limit or malformed output | Safe fallback or failed extraction; no implicit approval |
| Missing subscription/refund/delivery fact | `ASK_USER` |
| Explicit contract violation | `BLOCK` |
| Modified amount or recurring terms | Authorization fingerprint mismatch |
| Expired authorization | Payment denied |
| Replayed authorization | Payment denied |
| Razorpay provider error | Safe provider error; no false success |

## Production evolution

A production version would move secrets to a managed vault, replace local SQLite with encrypted managed storage, use a transactional distributed replay store, authenticate every user and agent, sign server-to-server requests, add telemetry and alerts, and undergo formal payment-security review.

