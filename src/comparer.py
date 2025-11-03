from __future__ import annotations

from typing import Dict, Iterable

from .models import ComparisonReport, Conflict, CustomerReceivePaymentTerms


def compare_payment_terms(
    excel_terms: Iterable[CustomerReceivePaymentTerms],
    qb_terms: Iterable[CustomerReceivePaymentTerms],) -> ComparisonReport:

    excel_dict: Dict[str, PaymentTerm] = {term.child_id: term for term in excel_terms}
    qb_dict: Dict[str, PaymentTerm] = {term.child_id: term for term in qb_terms}
    excel_only = [
        term for child_id, term in excel_dict.items() if child_id not in qb_dict
    ]
    qb_only = [
        term for child_id, term in qb_dict.items() if child_id not in excel_dict
    ]

    conflicts = []
    for child_id in excel_dict.keys() & qb_dict.keys():
        excel_name = excel_dict[child_id].customer
        qb_name = qb_dict[child_id].customer
        if excel_name != qb_name:
            conflicts.append(
                Conflict(
                    record_id=child_id,
                    excel_name=excel_name,
                    qb_name=qb_name,
                    reason="name_mismatch",
                )
            )
        elif excel_dict[child_id].date != qb_dict[child_id].date:
            conflicts.append(
                Conflict(
                    record_id=child_id,
                    excel_name=excel_name,
                    qb_name=qb_name,
                    reason="date_mismatch",
                )
            )
        elif excel_dict[child_id].invoice_number != qb_dict[child_id].invoice_number:
            conflicts.append(
                Conflict(
                    record_id=child_id,
                    excel_name=excel_name,
                    qb_name=qb_name,
                    reason="invoice_number_mismatch",
                )
            )
    return ComparisonReport(
        excel_only=excel_only,
        qb_only=qb_only,
        conflicts=conflicts,
    )
