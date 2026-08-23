from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


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


class IntentContract(BaseModel):
    """The user-approved rules an AI shopper must follow."""

    product_type: str
    maximum_amount: float = Field(gt=0)
    currency: str = "INR"
    required_features: list[str] = Field(default_factory=list)
    subscription_allowed: bool = False
    refundable_required: bool = False
    delivery_deadline: Optional[date] = None


class TransactionProposal(BaseModel):
    """Facts extracted from a merchant listing or checkout page."""

    merchant: str
    product_name: str
    amount: float = Field(gt=0)
    currency: str = "INR"
    features: list[str] = Field(default_factory=list)
    subscription_enabled: Optional[bool] = None
    refundable: Optional[bool] = None
    delivery_date: Optional[date] = None


class VerificationResult(BaseModel):
    decision: Decision
    violations: list[ViolationCode] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)