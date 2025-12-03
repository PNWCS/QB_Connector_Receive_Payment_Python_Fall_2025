# Receive Payment Connector

## Setup Project
Once you forked and cloned the repo, run:
```bash
poetry install
```
to install dependencies.
Then write code in the src/ folder.

## Quality Check
To setup pre-commit hook (you only need to do this once):
```bash
poetry run pre-commit install
```
To manually run pre-commit checks:
```bash
poetry run pre-commit run --all-file
```
To manually run ruff check and auto fix:
```bash
poetry run ruff check --fix
```

## Test
Run
```bash
poetry run pytest
```

## Run
poetry run python -m src.cli --workbook company_data.xlsx

# Build Exe
poetry run pyinstaller --onefile --name payment_terms_cli --hidden-import win32timezone --hidden-import win32com.client build_exe.py

# Run Exe
payment_terms_cli.exe --workbook company_data.xlsx


# Example JSON

{
  "status": "success",
  "generated_at": "2025-12-03T19:03:24.720086+00:00",
  "same_payments": 12,
  "added_payments": [
  {
      "record_id": 7535,
      "customer_name": "Test1",
      "amount": 946.11,
      "invoice_number": "23-0305",
      "date": "2024-05-10",
      "source": "excel"
    },
    {
      "record_id": 7529,
      "customer_name": "Test1",
      "amount": 1882.26,
      "invoice_number": "23-0305",
      "date": "2024-05-03",
      "source": "excel"
    }
  ],
  "conflicts": [
    {
      "record_id": 7536,
      "excel_name": "NBT Group LTD",
      "qb_name": "NBT Group LTD",
      "excel_amount": 936.15,
      "qb_amount": 936.16,
      "excel_date": "2024-05-10",
      "qb_date": "2024-05-11",
      "excel_invoice_number": "23-0401",
      "qb_invoice_number": "23-0401",
      "reason": "data_mismatch"
    },
    {
      "record_id": 12345678,
      "excel_name": null,
      "qb_name": "Test3",
      "excel_amount": null,
      "qb_amount": 5000.0,
      "excel_date": null,
      "qb_date": "2025-10-23",
      "excel_invoice_number": null,
      "qb_invoice_number": "23-0403",
      "reason": "missing_in_excel"
    }
  ],
  "error": null
}
