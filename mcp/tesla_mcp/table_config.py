from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
EXCELS_DIR = ROOT_DIR / 'excels'

TABLE_FILES = {
    'credit_dossier.credit_balance_sheet': EXCELS_DIR / 'Audited_Financials_3_Years_Balance_Sheet.xlsx',
    'credit_dossier.credit_cashflow_statement': EXCELS_DIR / 'Audited_Financials_3_Years_Cashflow_Statement.xlsx',
    'credit_dossier.credit_income_statement': EXCELS_DIR / 'Audited_Financials_3_Years_Income_Statement.xlsx',
    'credit_dossier.credit_bank_statements': EXCELS_DIR / 'Bank_Statements_6_12_Months.xlsx',
    'credit_dossier.credit_net_worth_statement': EXCELS_DIR / 'Net_Worth_Statement.xlsx',
    'credit_dossier.credit_projected_financials': EXCELS_DIR / 'Projected_Financials_Next_3_Years.xlsx',
}

SECTION2_TABLES = (
    'credit_dossier.section2_customer_information',
    'credit_dossier.section2_ownership_structure',
)

SECTION3_TABLES = (
    'credit_dossier.section3_customer_financial_information_historical',
    'credit_dossier.section3a_financial_forecast',
    'credit_dossier.section3a_customer_facilities',
    'credit_dossier.section3a_other_financial_institution_exposure',
    'credit_dossier.section3a_collateral_guarantee_information',
    'credit_dossier.section3b_documentation_security_exceptions',
    'credit_dossier.section3b_covenant_description',
    'credit_dossier.section3b_credit_committee_resolution',
)

ALL_TABLES = tuple(TABLE_FILES.keys()) + SECTION2_TABLES + SECTION3_TABLES
