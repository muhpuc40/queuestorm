"""
Pydantic schemas for QueueStorm Investigator.

Enum values are taken verbatim from the Problem Statement (Section 7) and the
allowed_enums block of SUST_Preli_Sample_Cases.json. Any deviation in casing /
spelling / pluralisation is treated as a schema violation by the judge, so these
are the single source of truth.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Input enums (lenient: we accept anything for input fields and normalise later,
# because the harness may send unusual / malformed values that we must not crash
# on. We only *strictly* validate our own OUTPUT enums.)
# --------------------------------------------------------------------------- #
class TransactionEntry(BaseModel):
    transaction_id: Optional[str] = None
    timestamp: Optional[str] = None
    type: Optional[str] = None
    amount: Optional[float] = None
    counterparty: Optional[str] = None
    status: Optional[str] = None

    # Be tolerant of extra/odd fields rather than rejecting the whole request.
    model_config = {"extra": "allow"}


class AnalyzeRequest(BaseModel):
    ticket_id: str
    complaint: str
    language: Optional[str] = None
    channel: Optional[str] = None
    user_type: Optional[str] = None
    campaign_context: Optional[str] = None
    transaction_history: Optional[List[TransactionEntry]] = None
    metadata: Optional[dict] = None

    model_config = {"extra": "allow"}


# --------------------------------------------------------------------------- #
# Output enums (STRICT — these must match the spec exactly).
# --------------------------------------------------------------------------- #
class EvidenceVerdict(str, Enum):
    consistent = "consistent"
    inconsistent = "inconsistent"
    insufficient_data = "insufficient_data"


class CaseType(str, Enum):
    wrong_transfer = "wrong_transfer"
    payment_failed = "payment_failed"
    refund_request = "refund_request"
    duplicate_payment = "duplicate_payment"
    merchant_settlement_delay = "merchant_settlement_delay"
    agent_cash_in_issue = "agent_cash_in_issue"
    phishing_or_social_engineering = "phishing_or_social_engineering"
    other = "other"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Department(str, Enum):
    customer_support = "customer_support"
    dispute_resolution = "dispute_resolution"
    payments_ops = "payments_ops"
    merchant_operations = "merchant_operations"
    agent_operations = "agent_operations"
    fraud_risk = "fraud_risk"


class AnalyzeResponse(BaseModel):
    ticket_id: str
    relevant_transaction_id: Optional[str]
    evidence_verdict: EvidenceVerdict
    case_type: CaseType
    severity: Severity
    department: Department
    agent_summary: str
    recommended_next_action: str
    customer_reply: str
    human_review_required: bool
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    reason_codes: Optional[List[str]] = None

    # Use enum *values* (strings) when serialising, never the Enum repr.
    model_config = {"use_enum_values": True}


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
