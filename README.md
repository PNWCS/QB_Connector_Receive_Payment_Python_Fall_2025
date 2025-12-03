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

## RUN
poetry run python -m src.cli --workbook company_data.xlsx

# BUILD EXE
poetry run pyinstaller --onefile --name payment_terms_cli --hidden-import win32timezone --hidden-import win32com.client build_exe.py

# RUN EXE
payment_terms_cli.exe --workbook company_data.xlsx
