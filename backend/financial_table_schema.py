"""Code-defined schemas and seed examples for manufactured financial tables."""

FINANCIAL_TABLES = {
    'credit_dossier.credit_balance_sheet': {
        'columns': ['Particulars', 'FY 2022-23 (INR Lakh)', 'FY 2023-24 (INR Lakh)', 'FY 2024-25 (INR Lakh)'],
        'fallbackRows': [
            ['Share Capital', '500.00', '500.00', '500.00'],
            ['Reserves and Surplus', '2350.00', '3120.00', '4010.00'],
            ['Total Assets', '7800.00', '9100.00', '10850.00'],
        ],
    },
    'credit_dossier.credit_cashflow_statement': {
        'columns': ['Particulars', 'FY 2022-23', 'FY 2023-24', 'FY 2024-25'],
        'fallbackRows': [
            ['Net Profit Before Tax', '600.15', '750.30', '1000.70'],
            ['Net Cash from Operating Activities', '890.00', '1120.00', '1460.00'],
            ['Closing Cash Balance', '680.00', '840.00', '1120.00'],
        ],
    },
    'credit_dossier.credit_income_statement': {
        'columns': ['Particulars', 'FY 2022-23 (INR Lakh)', 'FY 2023-24 (INR Lakh)', 'FY 2024-25 (INR Lakh)'],
        'fallbackRows': [
            ['Revenue from Operations', '7200.50', '8500.75', '10200.90'],
            ['EBITDA', '980.00', '1260.00', '1650.00'],
            ['Profit After Tax', '520.00', '680.00', '890.00'],
        ],
    },
    'credit_dossier.credit_bank_statements': {
        'columns': ['Date', 'Opening Balance (INR Lakh)', 'Credits (INR Lakh)', 'Debits (INR Lakh)', 'Closing Balance (INR Lakh)', 'Inward Return Count', 'Remarks'],
        'fallbackRows': [
            ['01-Apr-2025', '1250.90', '800.75', '720.50', '1331.15', '0', 'Customer collections received'],
            ['02-Apr-2025', '1331.15', '640.20', '510.80', '1460.55', '0', 'Normal operating activity'],
            ['03-Apr-2025', '1460.55', '720.10', '815.40', '1365.25', '1', 'Supplier payment processed'],
        ],
    },
    'credit_dossier.credit_net_worth_statement': {
        'columns': ['Particulars', 'Book Value (INR Lakh)', 'Market Value (INR Lakh)', 'Ownership', 'Encumbrance'],
        'fallbackRows': [
            ['Factory Land and Building', '1800.00', '2200.00', 'Owned', 'Equitable mortgage'],
            ['Plant and Machinery', '1250.00', '1520.00', 'Owned', 'Hypothecation'],
            ['Investments and Deposits', '640.00', '700.00', 'Owned', 'Nil'],
        ],
    },
    'credit_dossier.credit_projected_financials': {
        'columns': ['Particulars', 'FY 2025-26', 'FY 2026-27', 'FY 2027-28'],
        'fallbackRows': [
            ['Revenue from Operations', '12500.00', '14500.00', '17000.00'],
            ['EBITDA', '2050.00', '2450.00', '3000.00'],
            ['Debt Service Coverage Ratio', '1.45', '1.62', '1.78'],
        ],
    },
}

FINANCIAL_TABLE_NAMES = tuple(FINANCIAL_TABLES.keys())
