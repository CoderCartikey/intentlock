from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


def normalize_currency(value: str | None) -> str | None:
    """
    Convert common currency names and symbols into ISO currency codes.

    Examples:
    ₹, rupee, rupees, rs. -> INR
    $, dollars -> USD
    €, euros -> EUR
    """

    if value is None:
        return None

    cleaned = value.strip().upper().replace(".", "")

    currency_aliases = {
        "₹": "INR",
        "RS": "INR",
        "INR": "INR",
        "RUPEE": "INR",
        "RUPEES": "INR",
        "INDIAN RUPEE": "INR",
        "INDIAN RUPEES": "INR",

        "$": "USD",
        "US$": "USD",
        "USD": "USD",
        "DOLLAR": "USD",
        "DOLLARS": "USD",
        "US DOLLAR": "USD",
        "US DOLLARS": "USD",

        "€": "EUR",
        "EUR": "EUR",
        "EURO": "EUR",
        "EUROS": "EUR",

        "£": "GBP",
        "GBP": "GBP",
        "POUND": "GBP",
        "POUNDS": "GBP",
        "BRITISH POUND": "GBP",
        "BRITISH POUNDS": "GBP",
    }

    return currency_aliases.get(cleaned, cleaned)


class Decision(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    ASK_USER = "ASK_USER"


class ViolationCode(str, Enum):
    AMOUNT_EXCEEDED = "AMOUNT_EXCEEDED"
    SUBSCRIPTION_PROHIBITED = "SUBSCRIPTION_PROHIBITED"
    REFUNDABILITY_REQUIRED = "REFUNDABILITY_REQUIRED"
    REQUIRED_FEATURE_MISSING = "REQUIRED_FEATURE_MISSING"
    DELIVERY_DEADLINE_MISSED = "DELIVERY_DEADLINE_MISSED"


class ExtractionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FALLBACK = "FALLBACK"
    FAILED = "FAILED"


class IntentContract(BaseModel):
    """Rules explicitly reviewed and approved by the user."""

    product_type: str
    maximum_amount: float = Field(gt=0)
    currency: str = "INR"
    required_features: list[str] = Field(default_factory=list)
    subscription_allowed: bool = False
    refundable_required: bool = False
    delivery_deadline: Optional[date] = None

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency_field(cls, value: str) -> str:
        normalized = normalize_currency(value)

        if not normalized:
            return "INR"

        return normalized


class IntentDraft(BaseModel):
    """Unapproved purchasing constraints extracted by AI."""

    source_text: str
    product_type: Optional[str] = None
    maximum_amount: Optional[float] = Field(default=None, gt=0)
    currency: Optional[str] = None
    required_features: list[str] = Field(default_factory=list)
    subscription_allowed: Optional[bool] = None
    refundable_required: Optional[bool] = None
    delivery_deadline: Optional[date] = None
    ambiguities: list[str] = Field(default_factory=list)

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency_field(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        return normalize_currency(value)


class IntentExtractionResult(BaseModel):
    status: ExtractionStatus
    provider: str
    model: Optional[str] = None
    draft: Optional[IntentDraft] = None
    error_code: Optional[str] = None


class TransactionProposal(BaseModel):
    """Facts extracted from a merchant listing or checkout."""

    merchant: str
    product_name: str
    amount: float = Field(gt=0)
    currency: str = "INR"
    features: list[str] = Field(default_factory=list)
    subscription_enabled: Optional[bool] = None
    refundable: Optional[bool] = None
    delivery_date: Optional[date] = None

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency_field(cls, value: str) -> str:
        normalized = normalize_currency(value)

        if not normalized:
            return "INR"

        return normalized


class VerificationResult(BaseModel):
    decision: Decision
    violations: list[ViolationCode] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)