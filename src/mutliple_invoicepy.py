import re
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import List, Tuple, Optional, Dict



_XML10_ILLEGAL = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x84\x86-\x9F]")


def _strip_illegal_xml_chars(s):
    if s is None:
        return ""
    return _XML10_ILLEGAL.sub("", str(s))


def _esc(s):
    s = _strip_illegal_xml_chars(s)
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
         .replace("'", "&apos;")
    )


def _qb_date(s):
    if not s:
        return datetime.today().date().isoformat()
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%m-%d-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Unsupported date format for TxnDate: {s}")


def _qb_amount(x):
    if x is None or x == "":
        raise ValueError("Amount is required")
    d = Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    s = format(d, "f")
    if "." not in s:
        s += ".00"
    else:
        w, f = s.split(".", 1)
        s = f"{w}.{(f + '00')[:2]}"
    return s


def _qb_memo(memo):
    if not memo:
        return ""
    return _esc(memo)


def add_payment_term(company_file: str | None, term: "CustomerReceivePaymentTerms") -> "CustomerReceivePaymentTerms":
    """
    Creates a single ReceivePayment that applies to all open invoices for the given
    customer + invoice_number (RefNumber).

    If term.amount is provided, it will be allocated across invoices (oldest first).
    If not provided, it pays all open balances.

    Returns a term with amount set to the total applied and with .payment_txn_id if created.
    """
    customer = term.customer
    inv_ref = term.invoice_number  

    if not customer:
        raise ValueError("term.customer is required")
    if not inv_ref:
        raise ValueError("term.invoice_number is required")

    date_s = _qb_date(term.date)
    memo_src = term.memo if getattr(term, "memo", None) else (term.child_id or "")
    memo_x = _esc(memo_src)
    customer_x = _esc(customer)
    inv_ref_x = _esc(inv_ref)

    # ---------- 1) Query ALL matching invoices for this customer + RefNumber ----------
    inv_query = f"""<?xml version="1.0" encoding="utf-8"?>
<?qbxml version="16.0"?>
<QBXML>
  <QBXMLMsgsRq onError="stopOnError">
    <InvoiceQueryRq>
      <RefNumber>{inv_ref_x}</RefNumber>
      <OwnerID>0</OwnerID>
    </InvoiceQueryRq>
  </QBXMLMsgsRq>
</QBXML>"""

    try:
        ET.fromstring(inv_query)
    except ET.ParseError as e:
        raise RuntimeError(f"Local XML error (InvoiceQueryRq): {e}\n---\n{inv_query}\n---")

    root = _send_qbxml(inv_query)
    invoices = root.findall(".//InvoiceRet")

    # Collect unpaid/open-balance invoices with ordering (oldest first)
    def _to_dec(x, default="0"):
        try:
            return Decimal(str(x))
        except Exception:
            return Decimal(default)

    open_invoices = []
    for inv in invoices:
        txnid = (inv.findtext("TxnID") or "").strip()
        # Prefer TxnDate; fall back to TimeCreated
        txn_date_str = (inv.findtext("TxnDate") or "").strip()
        time_created = (inv.findtext("TimeCreated") or "").strip()
        bal_str = (inv.findtext("BalanceRemaining") or "0").strip()
        is_paid = (inv.findtext("IsPaid") or "").strip().lower() == "true"
        bal = _to_dec(bal_str)

        if txnid and bal > Decimal("0") and not is_paid:
            # Parse ordering keys
            try:
                dt_key = datetime.strptime(txn_date_str, "%Y-%m-%d")
            except Exception:
                # Example TimeCreated: 2025-10-23T12:59:57-06:00
                try:
                    dt_key = datetime.fromisoformat(time_created.replace("Z", "+00:00")) if time_created else datetime.max
                except Exception:
                    dt_key = datetime.max

            open_invoices.append(
                {
                    "TxnID": txnid,
                    "BalanceRemaining": bal,
                    "date_key": dt_key,
                    "time_created": time_created,
                }
            )

    if not open_invoices:
        # Nothing to pay — either already paid or not found
        return CustomerReceivePaymentTerms(
            child_id=term.child_id,
            customer=term.customer,
            invoice_number=term.invoice_number,
            amount=Decimal("0.00"),
            date=term.date,
            source="quickbooks",
        )

    open_invoices.sort(key=lambda x: (x["date_key"], x["time_created"]))

    # ---------- 2) Decide how much to apply ----------
    # If term.amount is provided: allocate across invoices in order.
    # If not: pay all open balances.
    allocations: List[Tuple[str, Decimal]] = []

    if getattr(term, "amount", None) is None:
        # Pay all balances
        for inv in open_invoices:
            allocations.append((inv["TxnID"], inv["BalanceRemaining"]))
    else:
        remaining = _to_dec(term.amount)
        if remaining <= 0:
            raise ValueError("term.amount must be > 0 when provided")
        for inv in open_invoices:
            if remaining <= 0:
                break
            apply_amt = min(inv["BalanceRemaining"], remaining)
            if apply_amt > 0:
                allocations.append((inv["TxnID"], apply_amt))
                remaining -= apply_amt

    if not allocations:
        # amount provided but zero after allocation
        return CustomerReceivePaymentTerms(
            child_id=term.child_id,
            customer=term.customer,
            invoice_number=term.invoice_number,
            amount=Decimal("0.00"),
            date=term.date,
            memo=getattr(term, "memo", None),
            source="quickbooks",
        )

    total_amount = sum(a for _, a in allocations)
    total_amount_s = _qb_amount(total_amount)

    # ---------- 3) Build ReceivePaymentAdd with multiple AppliedToTxnAdd ----------
    applied_xml = []
    for txnid, amt in allocations:
        applied_xml.append(
            f"""<AppliedToTxnAdd>
        <TxnID>{_esc(txnid)}</TxnID>
        <PaymentAmount>{_qb_amount(amt)}</PaymentAmount>
      </AppliedToTxnAdd>"""
        )
    applied_block = "\n      ".join(applied_xml)

    rp_add = f"""<?xml version="1.0" encoding="utf-8"?>
<?qbxml version="16.0"?>
<QBXML>
  <QBXMLMsgsRq onError="stopOnError">
    <ReceivePaymentAddRq>
      <ReceivePaymentAdd>
        <CustomerRef>
          <FullName>{customer_x}</FullName>
        </CustomerRef>
        <TxnDate>{_esc(date_s)}</TxnDate>
        <TotalAmount>{_esc(total_amount_s)}</TotalAmount>
        <Memo>{memo_x}</Memo>
        {applied_block}
      </ReceivePaymentAdd>
    </ReceivePaymentAddRq>
  </QBXMLMsgsRq>
</QBXML>"""

    try:
        ET.fromstring(rp_add)
    except ET.ParseError as e:
        raise RuntimeError(f"Local XML error (ReceivePaymentAddRq): {e}\n---\n{rp_add}\n---")

    rp_root = _send_qbxml(rp_add)
    tx = rp_root.find(".//ReceivePaymentRet/TxnID")
    if tx is not None and (tx.text or "").strip():
        try:
            setattr(term, "payment_txn_id", tx.text.strip())
        except Exception:
            pass

    # reflect the total applied in the returned term
    return CustomerReceivePaymentTerms(
        child_id=term.child_id,
        customer=term.customer,
        invoice_number=term.invoice_number,
        amount=Decimal(total_amount_s),
        date=term.date,
        source="quickbooks",
    )
