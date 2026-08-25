import os
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from pathlib import Path
from typing import Optional

import httpx
from pydantic import BaseModel

from app.authorization import (
    verify_payment_authorization,
)
from app.models import TransactionProposal


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = (
    PROJECT_ROOT / "data" / "intentlock.db"
)


class PaymentExecutionStatus(str, Enum):
    ORDER_CREATED = "ORDER_CREATED"
    DENIED = "DENIED"
    PROVIDER_ERROR = "PROVIDER_ERROR"


class PaymentExecutionError(str, Enum):
    INVALID_AUTHORIZATION = "INVALID_AUTHORIZATION"
    TOKEN_ALREADY_USED = "TOKEN_ALREADY_USED"
    RAZORPAY_NOT_CONFIGURED = "RAZORPAY_NOT_CONFIGURED"
    LIVE_KEY_PROHIBITED = "LIVE_KEY_PROHIBITED"
    UNSUPPORTED_PROVIDER = "UNSUPPORTED_PROVIDER"
    PROVIDER_REQUEST_FAILED = "PROVIDER_REQUEST_FAILED"


class PaymentExecutionResult(BaseModel):
    status: PaymentExecutionStatus
    provider: str
    order_id: Optional[str] = None
    authorization_id: Optional[str] = None
    receipt_id: Optional[str] = None
    error_code: Optional[PaymentExecutionError] = None
    authorization_error: Optional[str] = None


def initialize_payment_database(
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> None:
    database_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS payment_authorizations (
                authorization_id TEXT PRIMARY KEY,
                receipt_id TEXT NOT NULL,
                transaction_fingerprint TEXT NOT NULL,
                provider TEXT NOT NULL,
                status TEXT NOT NULL,
                order_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        connection.commit()


def _reserve_authorization(
    authorization_id: str,
    receipt_id: str,
    fingerprint: str,
    provider: str,
    database_path: Path,
) -> bool:
    """
    Atomically reserve an authorization before calling Razorpay.

    The PRIMARY KEY prevents two requests from consuming the same
    authorization token.
    """

    initialize_payment_database(database_path)

    current_time = datetime.now(timezone.utc).isoformat()

    try:
        with sqlite3.connect(
            database_path,
            timeout=10,
        ) as connection:
            connection.execute("BEGIN IMMEDIATE")

            connection.execute(
                """
                INSERT INTO payment_authorizations (
                    authorization_id,
                    receipt_id,
                    transaction_fingerprint,
                    provider,
                    status,
                    order_id,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    authorization_id,
                    receipt_id,
                    fingerprint,
                    provider,
                    "RESERVED",
                    None,
                    current_time,
                    current_time,
                ),
            )

            connection.commit()

        return True

    except sqlite3.IntegrityError:
        return False


def _update_authorization_status(
    authorization_id: str,
    status: str,
    database_path: Path,
    order_id: Optional[str] = None,
) -> None:
    current_time = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE payment_authorizations
            SET status = ?,
                order_id = ?,
                updated_at = ?
            WHERE authorization_id = ?
            """,
            (
                status,
                order_id,
                current_time,
                authorization_id,
            ),
        )

        connection.commit()


def _amount_to_subunits(amount: float) -> int:
    decimal_amount = Decimal(str(amount))

    subunits = (
        decimal_amount * Decimal("100")
    ).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    return int(subunits)


def _get_razorpay_credentials() -> tuple[str, str]:
    key_id = os.getenv("RAZORPAY_KEY_ID", "").strip()
    key_secret = os.getenv(
        "RAZORPAY_KEY_SECRET",
        "",
    ).strip()

    if not key_id or not key_secret:
        raise RuntimeError("RAZORPAY_NOT_CONFIGURED")

    if not key_id.startswith("rzp_test_"):
        raise RuntimeError("LIVE_KEY_PROHIBITED")

    return key_id, key_secret


def _create_mock_order(
    authorization_id: str,
) -> str:
    suffix = authorization_id.replace(
        "AUTH-",
        "",
    ).lower()

    return f"order_mock_{suffix}"


def _create_razorpay_order(
    transaction: TransactionProposal,
    receipt_id: str,
    authorization_id: str,
) -> str:
    key_id, key_secret = _get_razorpay_credentials()

    response = httpx.post(
        "https://api.razorpay.com/v1/orders",
        auth=(key_id, key_secret),
        json={
            "amount": _amount_to_subunits(
                transaction.amount
            ),
            "currency": transaction.currency,
            "receipt": receipt_id[:40],
            "notes": {
                "intentlock_authorization": (
                    authorization_id
                ),
                "intentlock_protected": "true",
                "merchant": transaction.merchant[:256],
                "product": transaction.product_name[:256],
            },
            "partial_payment": False,
        },
        timeout=10.0,
    )

    response.raise_for_status()

    response_data = response.json()
    order_id = response_data.get("id")

    if not order_id:
        raise RuntimeError(
            "Razorpay response did not contain an order ID"
        )

    return str(order_id)


def execute_payment_authorization(
    token: str,
    transaction: TransactionProposal,
    provider: str = "mock",
    database_path: Path = DEFAULT_DATABASE_PATH,
    signing_secret: Optional[str] = None,
    now: Optional[datetime] = None,
) -> PaymentExecutionResult:
    """
    Execute an authorized payment order.

    This is the only function that should be allowed to call
    the payment provider.
    """

    authorization_check = verify_payment_authorization(
        token=token,
        transaction=transaction,
        secret=signing_secret,
        now=now,
    )

    if (
        not authorization_check.valid
        or authorization_check.payload is None
    ):
        authorization_error = None

        if authorization_check.error_code:
            authorization_error = (
                authorization_check.error_code.value
            )

        return PaymentExecutionResult(
            status=PaymentExecutionStatus.DENIED,
            provider=provider,
            error_code=(
                PaymentExecutionError.INVALID_AUTHORIZATION
            ),
            authorization_error=authorization_error,
        )

    payload = authorization_check.payload

    if provider not in {"mock", "razorpay"}:
        return PaymentExecutionResult(
            status=PaymentExecutionStatus.DENIED,
            provider=provider,
            authorization_id=payload.authorization_id,
            receipt_id=payload.receipt_id,
            error_code=(
                PaymentExecutionError.UNSUPPORTED_PROVIDER
            ),
        )

    if provider == "razorpay":
        try:
            _get_razorpay_credentials()

        except RuntimeError as error:
            error_name = str(error)

            if error_name == "LIVE_KEY_PROHIBITED":
                error_code = (
                    PaymentExecutionError.LIVE_KEY_PROHIBITED
                )
            else:
                error_code = (
                    PaymentExecutionError.RAZORPAY_NOT_CONFIGURED
                )

            return PaymentExecutionResult(
                status=PaymentExecutionStatus.DENIED,
                provider=provider,
                authorization_id=payload.authorization_id,
                receipt_id=payload.receipt_id,
                error_code=error_code,
            )

    reserved = _reserve_authorization(
        authorization_id=payload.authorization_id,
        receipt_id=payload.receipt_id,
        fingerprint=payload.transaction_fingerprint,
        provider=provider,
        database_path=database_path,
    )

    if not reserved:
        return PaymentExecutionResult(
            status=PaymentExecutionStatus.DENIED,
            provider=provider,
            authorization_id=payload.authorization_id,
            receipt_id=payload.receipt_id,
            error_code=(
                PaymentExecutionError.TOKEN_ALREADY_USED
            ),
        )

    try:
        if provider == "mock":
            order_id = _create_mock_order(
                payload.authorization_id
            )
        else:
            order_id = _create_razorpay_order(
                transaction=transaction,
                receipt_id=payload.receipt_id,
                authorization_id=payload.authorization_id,
            )

    except Exception:
        _update_authorization_status(
            authorization_id=payload.authorization_id,
            status="PROVIDER_FAILED",
            database_path=database_path,
        )

        return PaymentExecutionResult(
            status=PaymentExecutionStatus.PROVIDER_ERROR,
            provider=provider,
            authorization_id=payload.authorization_id,
            receipt_id=payload.receipt_id,
            error_code=(
                PaymentExecutionError.PROVIDER_REQUEST_FAILED
            ),
        )

    _update_authorization_status(
        authorization_id=payload.authorization_id,
        status="ORDER_CREATED",
        database_path=database_path,
        order_id=order_id,
    )

    return PaymentExecutionResult(
        status=PaymentExecutionStatus.ORDER_CREATED,
        provider=provider,
        order_id=order_id,
        authorization_id=payload.authorization_id,
        receipt_id=payload.receipt_id,
    )