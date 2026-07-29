FINANCIAL_TABLE_NAMES = (
    'credit_dossier.credit_balance_sheet',
    'credit_dossier.credit_cashflow_statement',
    'credit_dossier.credit_income_statement',
    'credit_dossier.credit_bank_statements',
    'credit_dossier.credit_net_worth_statement',
    'credit_dossier.credit_projected_financials',
)

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

ALL_TABLES = FINANCIAL_TABLE_NAMES + SECTION2_TABLES + SECTION3_TABLES