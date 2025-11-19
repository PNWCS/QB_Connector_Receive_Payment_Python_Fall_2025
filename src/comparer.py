from __future__ import annotations

from typing import Dict, Iterable

from .models import ComparisonReport, Conflict, CustomerReceivePaymentTerms


def compare_payment_terms(
    excel_terms: Iterable[CustomerReceivePaymentTerms],
    qb_terms: Iterable[CustomerReceivePaymentTerms],
) -> ComparisonReport:
    excel_dict: Dict[int, CustomerReceivePaymentTerms] = {
        term.child_id: term for term in excel_terms
    }
    qb_dict: Dict[int, CustomerReceivePaymentTerms] = {
        term.child_id: term for term in qb_terms
    }
    excel_only = [
        term for child_id, term in excel_dict.items() if child_id not in qb_dict
    ]
    qb_only = [term for child_id, term in qb_dict.items() if child_id not in excel_dict]

    conflicts = []
    for child_id in excel_dict.keys() & qb_dict.keys():
        reasons = []
        excel_name = excel_dict[child_id].customer
        qb_name = qb_dict[child_id].customer
        if excel_name != qb_name:
            reasons.append("name_mismatch")
        if excel_dict[child_id].date != qb_dict[child_id].date:
            reasons.append("date_mismatch")
        if excel_dict[child_id].invoice_number != qb_dict[child_id].invoice_number:
            reasons.append("invoice_number_mismatch")
        if excel_dict[child_id].amount != qb_dict[child_id].amount:
            print(type(excel_dict[child_id].amount), type(qb_dict[child_id].amount))
            reasons.append("amount_mismatch")
        if len(reasons) != 0:
            conflicts.append(
                Conflict(
                    record_id=child_id,
                    excel_name=excel_name,
                    qb_name=qb_name,
                    excel_amount=excel_dict[child_id].amount,
                    qb_amount=qb_dict[child_id].amount,
                    excel_date=excel_dict[child_id].date,
                    qb_date=qb_dict[child_id].date,
                    excel_invoice_number=excel_dict[child_id].invoice_number,
                    qb_invoice_number=qb_dict[child_id].invoice_number,
                    reason="data_mismatch",
                )
            )

    return ComparisonReport(
        excel_only=excel_only,
        qb_only=qb_only,
        conflicts=conflicts,
    )
