import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from app.models import (
    Decision,
    TransactionProposal,
    VerificationResult,
)


class AuthorizationError(str, Enum):
    MALFORMED_TOKEN = "MALFORMED_TOKEN"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    EXPIRED_TOKEN = "EXPIRED_TOKEN"
    TRANSACTION_MISMATCH = "TRANSACTION_MISMATCH"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"


class PaymentAuthorizationPayload(BaseModel):
    authorization_id: str
    receipt_id: str
    transaction_fingerprint: str
    issued_at: datetime
    expires_at: datetime


class AuthorizationVerification(BaseModel):
    valid: bool
    error_code: Optional[AuthorizationError] = None
    payload: Optional[PaymentAuthorizationPayload] = None


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _base64_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _resolve_secret(secret: Optional[str]) -> bytes:
    selected_secret = secret or os.getenv(
        "INTENTLOCK_SIGNING_SECRET"
    )

    if not selected_secret:
        raise RuntimeError(
            "INTENTLOCK_SIGNING_SECRET is missing"
        )

    if len(selected_secret) < 32:
        raise RuntimeError(
            "INTENTLOCK_SIGNING_SECRET must contain "
            "at least 32 characters"
        )

    return selected_secret.encode("utf-8")


def transaction_fingerprint(
    transaction: TransactionProposal,
) -> str:
    """
    Create a stable SHA-256 fingerprint of every payment-relevant
    transaction field.
    """

    transaction_data = transaction.model_dump(mode="json")

    canonical_json = json.dumps(
        transaction_data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical_json.encode("utf-8")
    ).hexdigest()


def create_payment_authorization(
    transaction: TransactionProposal,
    verification_result: VerificationResult,
    receipt_id: str,
    expires_in_seconds: int = 300,
    secret: Optional[str] = None,
    now: Optional[datetime] = None,
) -> str:
    """
    Create a signed authorization only for an ALLOW decision.
    """

    if verification_result.decision != Decision.ALLOW:
        raise ValueError(
            "Payment authorization requires an ALLOW decision"
        )

    if expires_in_seconds <= 0:
        raise ValueError(
            "Authorization lifetime must be greater than zero"
        )

    issued_at = _ensure_utc(
        now or datetime.now(timezone.utc)
    )

    payload = PaymentAuthorizationPayload(
        authorization_id=f"AUTH-{secrets.token_hex(8).upper()}",
        receipt_id=receipt_id,
        transaction_fingerprint=transaction_fingerprint(
            transaction
        ),
        issued_at=issued_at,
        expires_at=issued_at + timedelta(
            seconds=expires_in_seconds
        ),
    )

    payload_json = json.dumps(
        payload.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    encoded_payload = _base64_encode(payload_json)

    signature = hmac.new(
        _resolve_secret(secret),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()

    encoded_signature = _base64_encode(signature)

    return f"{encoded_payload}.{encoded_signature}"


def verify_payment_authorization(
    token: str,
    transaction: TransactionProposal,
    secret: Optional[str] = None,
    now: Optional[datetime] = None,
) -> AuthorizationVerification:
    """
    Verify signature, expiry and exact transaction binding.

    Any failure returns valid=False. Payment execution must stop.
    """

    try:
        encoded_payload, encoded_signature = token.split(".")

        supplied_signature = _base64_decode(
            encoded_signature
        )

    except (ValueError, TypeError):
        return AuthorizationVerification(
            valid=False,
            error_code=AuthorizationError.MALFORMED_TOKEN,
        )

    try:
        signing_secret = _resolve_secret(secret)

    except RuntimeError:
        return AuthorizationVerification(
            valid=False,
            error_code=AuthorizationError.CONFIGURATION_ERROR,
        )

    expected_signature = hmac.new(
        signing_secret,
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()

    if not hmac.compare_digest(
        supplied_signature,
        expected_signature,
    ):
        return AuthorizationVerification(
            valid=False,
            error_code=AuthorizationError.INVALID_SIGNATURE,
        )

    try:
        payload_data = json.loads(
            _base64_decode(encoded_payload)
        )

        payload = PaymentAuthorizationPayload.model_validate(
            payload_data
        )

    except Exception:
        return AuthorizationVerification(
            valid=False,
            error_code=AuthorizationError.MALFORMED_TOKEN,
        )

    current_time = _ensure_utc(
        now or datetime.now(timezone.utc)
    )

    expires_at = _ensure_utc(payload.expires_at)

    if current_time >= expires_at:
        return AuthorizationVerification(
            valid=False,
            error_code=AuthorizationError.EXPIRED_TOKEN,
            payload=payload,
        )

    current_fingerprint = transaction_fingerprint(
        transaction
    )

    if not hmac.compare_digest(
        payload.transaction_fingerprint,
        current_fingerprint,
    ):
        return AuthorizationVerification(
            valid=False,
            error_code=AuthorizationError.TRANSACTION_MISMATCH,
            payload=payload,
        )

    return AuthorizationVerification(
        valid=True,
        payload=payload,
    )