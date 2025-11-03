from pathlib import Path
from src.excel_reader import read_CustomerReceivePaymentTerms_from_excel
from src.qb_gateway import fetch_payment_terms
from src.comparer import compare_payment_terms
from src.runner import run_payment_terms
from src.models import CustomerReceivePaymentTerms
import traceback

def main():
    test=run_payment_terms(
        company_file_path="",
    workbook_path="company_data.xlsx",
        output_path="payment_terms_report.json",
    )
    print(test)


   
   
if __name__ == "__main__":
    main()
