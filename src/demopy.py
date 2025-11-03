
import re
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

# ===== Helpers =====

_XML10_ILLEGAL = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x84\x86-\x9F]")

def _strip_illegal_xml_chars(s):
    if s is None:
        return ""
    return _XML10_ILLEGAL.sub("", str(s))

def _esc(s):
    s = _strip_illegal_xml_chars(s)
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&apos;"))

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

# ===== Main =====

def add_payment_term(company_file: str | None, term: CustomerReceivePaymentTerms) -> CustomerReceivePaymentTerms:
    customer = term.customer
    inv_ref  = term.invoice_number  # human invoice number (RefNumber)
    amount   = term.amount
    if not customer:      raise ValueError("term.customer is required")
    if not inv_ref:       raise ValueError("term.invoice_number is required")
    amount_s = _qb_amount(amount)
    date_s   = _qb_date(term.date)
    memo_src =  term.child_id or ""

    customer_x = _esc(customer)
    memo_x     = _esc(memo_src)
    amount_x   = _esc(amount_s)
    date_x     = _esc(date_s)
    inv_ref_x  = _esc(inv_ref)

    # ---- 1) Ensure we have the invoice TxnID ----
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
    node = root.find(".//InvoiceRet/TxnID")
    if node is None or not (node.text or "").strip():
        raise RuntimeError(f"Invoice '{inv_ref}' not found or not unique.")
    inv_txnid = node.text.strip()
    try: setattr(term, "invoice_txn_id", inv_txnid)
    except Exception: pass

    inv_txnid_x = _esc(inv_txnid)
    rp_add = f"""<?xml version="1.0" encoding="utf-8"?>
<?qbxml version="16.0"?>
<QBXML>
  <QBXMLMsgsRq onError="stopOnError">
    <ReceivePaymentAddRq>
      <ReceivePaymentAdd>
        <CustomerRef>
          <FullName>{customer_x}</FullName>
        </CustomerRef>
        <TxnDate>{date_x}</TxnDate>
        <TotalAmount>{amount_x}</TotalAmount>
        <Memo>{memo_x}</Memo>
        <AppliedToTxnAdd>
          <TxnID>{inv_txnid_x}</TxnID>
          <PaymentAmount>{amount_x}</PaymentAmount>
        </AppliedToTxnAdd>
      </ReceivePaymentAdd>
    </ReceivePaymentAddRq>
  </QBXMLMsgsRq>
</QBXML>"""

    try:
        ET.fromstring(rp_add)
    except ET.ParseError as e:
        raise RuntimeError(f"Local XML error (ReceivePaymentAddRq): {e}\n---\n{rp_add}\n---")

    try:
        rp_root = _send_qbxml(rp_add)
    except RuntimeError as exc:
        # Check if error is "name already in use" (error code 3100)
        if "already in use" in str(exc):
            # Return the term as-is since it already exists
            return CustomerReceivePaymentTerms(
                child_id=term.child_id, customer=term.customer, invoice_number=term.invoice_number, amount=term.amount, date=term.date, memo=term.memo, invoice_txn_id=term.invoice_txn_id, source="quickbooks"
            )
        raise

    tx = rp_root.find(".//ReceivePaymentRet/TxnID")
    if tx is not None and (tx.text or "").strip():
        try: setattr(term, "payment_txn_id", tx.text.strip())
        except Exception: pass

    return CustomerReceivePaymentTerms(
        child_id=term.child_id,
        customer=term.customer,
        invoice_number=term.invoice_number,
        amount=term.amount,
        date=term.date,
        source="quickbooks",)
        
