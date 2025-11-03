"""Domain models for payment term synchronisation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from datetime import date

SourceLiteral = Literal["excel", "quickbooks"]
ConflictReason = Literal["name_mismatch", "missing_in_excel", "missing_in_quickbooks"]


@dataclass(slots=True)
class CustomerReceivePaymentTerms:
    """Represents a payment term synchronised between Excel and QuickBooks."""
    customer: str
    date: date
    child_id: int
    invoice_number: str
    amount: float
    source: SourceLiteral


@dataclass(slots=True)
class Conflict:
    """Describes a discrepancy between Excel and QuickBooks payment terms."""

    record_id: str
    excel_name: str | None
    qb_name: str | None
    reason: ConflictReason


@dataclass(slots=True)
class ComparisonReport:
    """Groups comparison outcomes for later processing."""

    excel_only: list[CustomerReceivePaymentTerms] = field(default_factory=list)
    qb_only: list[CustomerReceivePaymentTerms] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)


__all__ = [
    "CustomerReceivePaymentTerms",
    "Conflict",
    "ComparisonReport",
    "ConflictReason",
    "SourceLiteral",
]