from __future__ import annotations
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from typing import Iterator, List
from .models import CustomerReceivePaymentTerms
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import re


try:
    import win32com.client  # type: ignore
except ImportError:  # pragma: no cover
    win32com = None  # type: ignore

APP_NAME = "Quickbooks Connector"  # do not chanege this


def _require_win32com() -> None:
    if win32com is None:  # pragma: no cover - exercised via tests
        raise RuntimeError("pywin32 is required to communicate with QuickBooks")

@contextmanager
def _qb_session() -> Iterator[tuple[object, object]]:
    _require_win32com()
    session = win32com.client.Dispatch("QBXMLRP2.RequestProcessor")
    session.OpenConnection2("", APP_NAME, 1)
    ticket = session.BeginSession("", 0)
    try:
        yield session, ticket
    finally:
        try:
            session.EndSession(ticket)
        finally:
            session.CloseConnection()

def _send_qbxml(qbxml: str) -> ET.Element:
    with _qb_session() as (session, ticket):
        #print(f"Sending QBXML:\n{qbxml}")  # Debug output
        raw_response = session.ProcessRequest(ticket, qbxml)  # type: ignore[attr-defined]
        # print(f"Received response:\n{raw_response}")  # Debug output
    return _parse_response(raw_response)


def _parse_response(raw_xml: str) -> ET.Element:
    root = ET.fromstring(raw_xml)
    response = root.find(".//*[@statusCode]")
    if response is None:
        raise RuntimeError("QuickBooks response missing status information")

    status_code = int(response.get("statusCode", "0"))
    status_message = response.get("statusMessage", "")
    # Status code 1 means "no matching objects found" - this is OK for queries
    if status_code != 0 and status_code != 1:
        print(f"QuickBooks error ({status_code}): {status_message}")
        raise RuntimeError(status_message)
    return response


def fetch_payment_terms(company_file: str | None = None) -> List[CustomerReceivePaymentTerms]:
    """Return payment terms currently stored in QuickBooks."""

    qbxml = (
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
        "<?qbxml version=\"16.0\"?>"
        "<QBXML>"
        "  <QBXMLMsgsRq onError=\"continueOnError\">"
        "    <ReceivePaymentQueryRq>"
        "      <IncludeLineItems>1</IncludeLineItems>"
        "    </ReceivePaymentQueryRq>"
        "  </QBXMLMsgsRq>"
        "</QBXML>"
    )
    root = _send_qbxml(qbxml)
    payments: list[CustomerReceivePaymentTerms] = []
    for pay_ret in root.findall(".//ReceivePaymentRet"):
        memo = (pay_ret.findtext("Memo") or "").strip()
        fullname = (pay_ret.findtext("./CustomerRef/FullName") or "").strip()
        txndate = (pay_ret.findtext("TxnDate") or "").strip()
        amount = (pay_ret.findtext("TotalAmount") or "").strip()

        applied_list = pay_ret.findall("./AppliedToTxnRet")
        # if not applied_list:
        #     # If no AppliedToTxnRet, still capture the payment-level fields
        #     payments.append(
        #         CustomerReceivePaymentTerms(
        #             child_id=memo,
        #             invoice_number=None,
        #             customer=fullname,
        #             date=txndate,
        #             amount=amount,
        #             source="quickbooks",
        #         )
        #     )
        #     continue

        # Create one record per applied transaction (common in QuickBooks)
        for applied in applied_list:
            ref_number = (applied.findtext("RefNumber") or "").strip()
            payments.append(
                CustomerReceivePaymentTerms(
                    child_id=memo,
                    invoice_number=ref_number if ref_number else None,
                    customer=fullname,
                    date=txndate,
                    amount=amount,
                    source="quickbooks",
                )
            )
    return payments



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

def add_payment_term(company_file: str | None, terms: List["CustomerReceivePaymentTerms"]) -> List[CustomerReceivePaymentTerms]:
    rp_add_reqs = []
    result:List[CustomerReceivePaymentTerms] = []
    for term in terms:
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
        total_amount_s = _qb_amount(term.amount)  # returns "0.00" string

        # Build <AppliedToTxnAdd> blocks for ALL matching invoices
        applied_xml = []
        for inv in invoices:
            txnid = (inv.findtext("TxnID") or "").strip()
            if not txnid:
                continue
            # If you have per-invoice amounts, put them here instead of total_amount_s
            applied_xml.append(
                f"""<AppliedToTxnAdd>
                    <TxnID>{_esc(txnid)}</TxnID>
                    <PaymentAmount>{_esc(total_amount_s)}</PaymentAmount>
                </AppliedToTxnAdd>"""
            )
        if not applied_xml:
            raise RuntimeError(f"No invoice TxnID(s) found for invoice reference: {inv_ref}")

        applied_block = "\n".join(applied_xml)

        # One ReceivePaymentAddRq per term
        rp_add_reqs.append(f"""
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
            </ReceivePaymentAddRq>""")


    # Envelope the whole batch
    batch_rp_add = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<?qbxml version="16.0"?>'
        '<QBXML>'
        '<QBXMLMsgsRq onError="stopOnError">'
        + "\n".join(rp_add_reqs) +
        '</QBXMLMsgsRq>'
        '</QBXML>'
    )

    # Validate XML locally
    try:
        ET.fromstring(batch_rp_add)
    except ET.ParseError as e:
        raise RuntimeError(f"Local XML error (ReceivePaymentAddRq): {e}\n---\n{batch_rp_add}\n---")

    # Send and parse response
    rp_root = _send_qbxml(batch_rp_add)

    # Map ALL returns back in order
    rets = rp_root.findall(".//ReceivePaymentRet")
    for pay_ret in rp_root.findall(".//ReceivePaymentRet"):
        memo = (pay_ret.findtext("Memo") or "").strip()
        fullname = (pay_ret.findtext("./CustomerRef/FullName") or "").strip()
        txndate = (pay_ret.findtext("TxnDate") or "").strip()
        amount = (pay_ret.findtext("TotalAmount") or "").strip()
        if not all((memo,fullname,txndate,amount)):
            continue
        applied_list = pay_ret.findall("./AppliedToTxnRet")
        for applied in applied_list:
            ref_number = (applied.findtext("RefNumber") or "").strip()
            result.append(
                CustomerReceivePaymentTerms(
                    child_id=memo,
                    invoice_number=ref_number if ref_number else None,
                    customer=fullname,
                    date=txndate,
                    amount=amount,
                    source="quickbooks",
                )
            )
    
       
    if not rets:
        raise RuntimeError("No ReceivePaymentRet nodes returned by QuickBooks.")
    return result
