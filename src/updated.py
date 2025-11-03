
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

def _to_dec(x, default="0"):
        try:
            return Decimal(str(x))
        except Exception:
            return Decimal(default)

def get_txn_id_from_payment_term(inv_ref_x: str) -> Optional[str]:
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
    return invoices

def add_payment_term(company_file: str | None, term: "CustomerReceivePaymentTerms") -> "CustomerReceivePaymentTerms":
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
    invoices = get_txn_id_from_payment_term(inv_ref_x)
    total_amount_s = _qb_amount(term.amount)

    applied_xml = []
    for inv in invoices:
        print(inv)
        txnid = (inv.findtext("TxnID") or "").strip()
    applied_xml.append(
            f"""<AppliedToTxnAdd>
        <TxnID>{_esc(txnid)}</TxnID>
        <PaymentAmount>{total_amount_s}</PaymentAmount>
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

    return CustomerReceivePaymentTerms(
        child_id=term.child_id,
        customer=term.customer,
        invoice_number=term.invoice_number,
        amount=Decimal(total_amount_s),
        date=term.date,
        source="quickbooks",
    )
