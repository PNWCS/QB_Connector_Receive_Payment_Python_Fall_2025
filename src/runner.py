"""High-level orchestration for the payment term CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from . import comparer, excel_reader, qb_gateway
from .models import Conflict, CustomerReceivePaymentTerms
from .reporting import iso_timestamp, write_report

DEFAULT_REPORT_NAME = "customer_payment_terms_report.json"


def _term_to_dict(term: CustomerReceivePaymentTerms) -> Dict[str, str]:
    return {"record_id": term.child_id, "name": term.customer, "source": term.source}


def _conflict_to_dict(conflict: Conflict) -> Dict[str, object]:
    return {
        "record_id": conflict.record_id,
        "excel_name": conflict.excel_name,
        "qb_name": conflict.qb_name,
        "reason": conflict.reason,
    }


def _missing_in_excel_conflict(term: CustomerReceivePaymentTerms) -> Dict[str, object]:
    return {
        "record_id": term.child_id,
        "excel_name": None,
        "qb_name": term.customer,
        "reason": "missing_in_excel",
    }


def run_payment_terms(
    company_file_path: str,
    workbook_path: str,
    *,
    output_path: str | None = None,
) -> Path:
    """Contract entry point for synchronising payment terms.

    Args:
        company_file_path: Path to the QuickBooks company file. Use an empty
            string to reuse the currently open company file.
        workbook_path: Path to the Excel workbook containing the
            payment_terms worksheet.
        output_path: Optional JSON output path. Defaults to
            payment_terms_report.json in the current working directory.

    Returns:
        Path to the generated JSON report.
    """

    report_path = Path(output_path) if output_path else Path(DEFAULT_REPORT_NAME)
    report_payload: Dict[str, object] = {
        "status": "success",
        "generated_at": iso_timestamp(),
        "added_terms": [],
        "conflicts": [],
        "error": None,
    }

    try:
        excel_terms = excel_reader.read_CustomerReceivePaymentTerms_from_excel(Path(workbook_path))
        qb_terms = qb_gateway.fetch_payment_terms(company_file_path)
        comparison = comparer.compare_payment_terms(excel_terms, qb_terms)
        print(comparison)

        added_terms = []
        errors = []
        try:    
            added_terms = qb_gateway.add_payment_term(company_file_path, comparison.excel_only)
        except Exception as e:
            errors.append(e)
        # for i, term in enumerate(comparison.excel_only, start=1):
        #     try:
        #         added = qb_gateway.add_payment_term(company_file_path, term)
        #         added_terms.append(added)
        #     except Exception as e:
        #         errors.append((i, term, e))

        

        conflicts: List[Dict[str, object]] = []
        conflicts.extend(
            _conflict_to_dict(conflict) for conflict in comparison.conflicts
        )
        conflicts.extend(
            _missing_in_excel_conflict(term) for term in comparison.qb_only
        )

        report_payload["added_terms"] = [_term_to_dict(term) for term in added_terms]
        report_payload["conflicts"] = conflicts
    except Exception as exc:  # pragma: no cover - behaviour verified via tests
        report_payload["status"] = "error"
        report_payload["error"] = str(exc)

    write_report(report_payload, report_path)
    return report_path


__all__ = ["run_payment_terms", "DEFAULT_REPORT_NAME"]