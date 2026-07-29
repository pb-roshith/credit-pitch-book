from database import ensure_database, get_connection
from load_section2_tables import CLIENT_ID, create_support_clients_table


SOURCE_DOCUMENT = 'Mistral PDF Library 019f561a-b2e6-7552-b9fe-1215aec0f20c'


def create_section3_tables(conn):
    conn.execute('CREATE SCHEMA IF NOT EXISTS credit_dossier;')
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS credit_dossier.section3_customer_financial_information_historical (
            financial_id BIGSERIAL PRIMARY KEY,
            client_id BIGINT NOT NULL REFERENCES credit_dossier.clients(client_id) ON DELETE CASCADE,
            statement_year INTEGER NOT NULL,
            statement_date DATE NOT NULL,
            statement_period_months INTEGER NOT NULL,
            audit_method TEXT NOT NULL,
            external_auditor TEXT,
            currency_code CHAR(3) NOT NULL DEFAULT 'GBP',
            unit_scale TEXT NOT NULL DEFAULT '000',
            sales_turnover NUMERIC(18, 2),
            sales_growth_pct NUMERIC(9, 4),
            gross_margin_pct NUMERIC(9, 4),
            net_operating_profit NUMERIC(18, 2),
            net_profit_before_tax_sales_pct NUMERIC(9, 4),
            net_profit NUMERIC(18, 2),
            ebitda NUMERIC(18, 2),
            net_cash_after_operations NUMERIC(18, 2),
            net_worth NUMERIC(18, 2),
            bank_borrowing NUMERIC(18, 2),
            total_liability NUMERIC(18, 2),
            total_assets NUMERIC(18, 2),
            debt_tangible_net_worth_pct NUMERIC(9, 4),
            accounts_receivable_days NUMERIC(9, 2),
            accounts_payable_days NUMERIC(9, 2),
            inventory_days NUMERIC(9, 2),
            interest_coverage NUMERIC(12, 4),
            source_document TEXT NOT NULL,
            source_pdf_pages INTEGER[] NOT NULL,
            data_quality_note TEXT,
            prepared_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (client_id, statement_year)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS credit_dossier.section3a_financial_forecast (
            forecast_id BIGSERIAL PRIMARY KEY,
            client_id BIGINT NOT NULL REFERENCES credit_dossier.clients(client_id) ON DELETE CASCADE,
            forecast_year INTEGER NOT NULL,
            forecast_label TEXT NOT NULL,
            currency_code CHAR(3) NOT NULL DEFAULT 'GBP',
            unit_scale TEXT NOT NULL DEFAULT '000',
            sales_turnover NUMERIC(18, 2),
            sales_growth_pct NUMERIC(9, 4),
            gross_margin_pct NUMERIC(9, 4),
            net_operating_profit NUMERIC(18, 2),
            net_profit_before_tax_sales_pct NUMERIC(9, 4),
            net_profit NUMERIC(18, 2),
            ebitda NUMERIC(18, 2),
            net_cash_after_operations NUMERIC(18, 2),
            net_worth NUMERIC(18, 2),
            bank_borrowing NUMERIC(18, 2),
            total_liability NUMERIC(18, 2),
            total_assets NUMERIC(18, 2),
            debt_tangible_net_worth_pct NUMERIC(9, 4),
            accounts_receivable_days NUMERIC(9, 2),
            accounts_payable_days NUMERIC(9, 2),
            inventory_days NUMERIC(9, 2),
            interest_coverage NUMERIC(12, 4),
            model_name TEXT NOT NULL,
            model_note TEXT,
            source_table TEXT NOT NULL,
            prepared_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (client_id, forecast_year)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS credit_dossier.section3a_customer_facilities (
            facility_id BIGSERIAL PRIMARY KEY,
            client_id BIGINT NOT NULL REFERENCES credit_dossier.clients(client_id) ON DELETE CASCADE,
            facility_type TEXT NOT NULL,
            facility_amount_existing NUMERIC(18, 2),
            utilization NUMERIC(18, 2),
            facility_amount_new NUMERIC(18, 2),
            currency_code CHAR(3) NOT NULL DEFAULT 'GBP',
            unit_scale TEXT NOT NULL DEFAULT '000',
            source_note TEXT,
            prepared_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (client_id, facility_type)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS credit_dossier.section3a_other_financial_institution_exposure (
            exposure_id BIGSERIAL PRIMARY KEY,
            client_id BIGINT NOT NULL REFERENCES credit_dossier.clients(client_id) ON DELETE CASCADE,
            exposure_type TEXT NOT NULL,
            exposure_limit NUMERIC(18, 2),
            exposure NUMERIC(18, 2),
            currency_code CHAR(3) NOT NULL DEFAULT 'GBP',
            unit_scale TEXT NOT NULL DEFAULT '000',
            source_note TEXT,
            prepared_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (client_id, exposure_type)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS credit_dossier.section3a_collateral_guarantee_information (
            collateral_id BIGSERIAL PRIMARY KEY,
            client_id BIGINT NOT NULL REFERENCES credit_dossier.clients(client_id) ON DELETE CASCADE,
            collateral_category TEXT NOT NULL,
            mitigant_type TEXT NOT NULL,
            amount NUMERIC(18, 2),
            currency_code CHAR(3) NOT NULL DEFAULT 'GBP',
            unit_scale TEXT NOT NULL DEFAULT '000',
            source_note TEXT,
            prepared_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (client_id, collateral_category, mitigant_type)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS credit_dossier.section3b_documentation_security_exceptions (
            exception_id BIGSERIAL PRIMARY KEY,
            client_id BIGINT NOT NULL REFERENCES credit_dossier.clients(client_id) ON DELETE CASCADE,
            exception_code TEXT NOT NULL,
            end_date DATE,
            mitigant_exception_description TEXT,
            exception_severity TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Open',
            source_note TEXT,
            prepared_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (client_id, exception_code)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS credit_dossier.section3b_covenant_description (
            covenant_id BIGSERIAL PRIMARY KEY,
            client_id BIGINT NOT NULL REFERENCES credit_dossier.clients(client_id) ON DELETE CASCADE,
            covenant_type TEXT NOT NULL,
            reporting_date DATE,
            due_date DATE,
            description TEXT NOT NULL,
            threshold_value TEXT,
            reported_value TEXT,
            compliance_status TEXT,
            source_document TEXT,
            source_pdf_pages INTEGER[],
            source_note TEXT,
            prepared_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (client_id, covenant_type, reporting_date)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS credit_dossier.section3b_credit_committee_resolution (
            resolution_id BIGSERIAL PRIMARY KEY,
            client_id BIGINT NOT NULL REFERENCES credit_dossier.clients(client_id) ON DELETE CASCADE,
            credit_committee_name TEXT NOT NULL,
            decision TEXT NOT NULL,
            resolution_by TEXT,
            meeting_date DATE,
            meeting_no TEXT,
            resolution_summary TEXT,
            final_approving_authority TEXT,
            source_note TEXT,
            prepared_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (client_id, credit_committee_name, meeting_no)
        );
        """
    )


def seed_historical_financials(conn):
    rows = [
        (CLIENT_ID, 2023, '2023-03-31', 12, 'Audited', 'Deloitte LLP', 'GBP', '000', 86250.00, 8.7500, 31.4000, 11240.00, 8.9200, 7695.00, 14180.00, 10460.00, 36220.00, 18850.00, 54200.00, 90420.00, 52.0500, 63.50, 51.20, 68.40, 5.8400, SOURCE_DOCUMENT, [21, 22], 'Audited statements reconciled to income statement, balance sheet and cash flow extracts.'),
        (CLIENT_ID, 2024, '2024-03-31', 12, 'Audited', 'Deloitte LLP', 'GBP', '000', 97480.00, 13.0200, 32.1000, 13225.00, 9.5500, 9310.00, 16440.00, 12175.00, 44780.00, 21320.00, 61250.00, 106030.00, 47.6100, 59.80, 49.50, 63.10, 6.3200, SOURCE_DOCUMENT, [23, 24], 'Working capital metrics calculated from audited year-end trade balances.'),
        (CLIENT_ID, 2025, '2025-03-31', 12, 'Audited', 'Deloitte LLP', 'GBP', '000', 111650.00, 14.5400, 32.8500, 15685.00, 10.1200, 11300.00, 19125.00, 14290.00, 55240.00, 24580.00, 69470.00, 124710.00, 44.5000, 56.20, 47.80, 59.60, 6.8900, SOURCE_DOCUMENT, [25, 26], 'FY2025 figures include normalization for one-time tooling income disclosed in notes.'),
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO credit_dossier.section3_customer_financial_information_historical (
                client_id, statement_year, statement_date, statement_period_months, audit_method,
                external_auditor, currency_code, unit_scale, sales_turnover, sales_growth_pct,
                gross_margin_pct, net_operating_profit, net_profit_before_tax_sales_pct,
                net_profit, ebitda, net_cash_after_operations, net_worth, bank_borrowing,
                total_liability, total_assets, debt_tangible_net_worth_pct,
                accounts_receivable_days, accounts_payable_days, inventory_days,
                interest_coverage, source_document, source_pdf_pages, data_quality_note
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (client_id, statement_year) DO UPDATE SET
                statement_date = EXCLUDED.statement_date,
                statement_period_months = EXCLUDED.statement_period_months,
                audit_method = EXCLUDED.audit_method,
                external_auditor = EXCLUDED.external_auditor,
                currency_code = EXCLUDED.currency_code,
                unit_scale = EXCLUDED.unit_scale,
                sales_turnover = EXCLUDED.sales_turnover,
                sales_growth_pct = EXCLUDED.sales_growth_pct,
                gross_margin_pct = EXCLUDED.gross_margin_pct,
                net_operating_profit = EXCLUDED.net_operating_profit,
                net_profit_before_tax_sales_pct = EXCLUDED.net_profit_before_tax_sales_pct,
                net_profit = EXCLUDED.net_profit,
                ebitda = EXCLUDED.ebitda,
                net_cash_after_operations = EXCLUDED.net_cash_after_operations,
                net_worth = EXCLUDED.net_worth,
                bank_borrowing = EXCLUDED.bank_borrowing,
                total_liability = EXCLUDED.total_liability,
                total_assets = EXCLUDED.total_assets,
                debt_tangible_net_worth_pct = EXCLUDED.debt_tangible_net_worth_pct,
                accounts_receivable_days = EXCLUDED.accounts_receivable_days,
                accounts_payable_days = EXCLUDED.accounts_payable_days,
                inventory_days = EXCLUDED.inventory_days,
                interest_coverage = EXCLUDED.interest_coverage,
                source_document = EXCLUDED.source_document,
                source_pdf_pages = EXCLUDED.source_pdf_pages,
                data_quality_note = EXCLUDED.data_quality_note;
            """,
            rows,
        )


def seed_forecast(conn):
    rows = [
        (CLIENT_ID, 2026, 'Base Case FY2026', 'GBP', '000', 125800.00, 12.6700, 33.1000, 18120.00, 10.6000, 13335.00, 22150.00, 16320.00, 68100.00, 28750.00, 79800.00, 147900.00, 42.2200, 55.00, 48.00, 58.00, 7.1500, 'Bank Base Case Forecast Model', 'Assumes 11 percent domestic OEM volume growth and steady export realization.', 'credit_dossier.section3_customer_financial_information_historical'),
        (CLIENT_ID, 2027, 'Base Case FY2027', 'GBP', '000', 140250.00, 11.4900, 33.4000, 20640.00, 11.0500, 15495.00, 25280.00, 18475.00, 84750.00, 32600.00, 90150.00, 174900.00, 38.4700, 54.00, 48.00, 57.00, 7.5200, 'Bank Base Case Forecast Model', 'Capacity expansion benefits assumed from new machining line commissioning.', 'credit_dossier.section3_customer_financial_information_historical'),
        (CLIENT_ID, 2028, 'Base Case FY2028', 'GBP', '000', 156300.00, 11.4400, 33.7000, 23420.00, 11.5000, 17975.00, 28610.00, 21100.00, 103850.00, 35500.00, 99150.00, 203000.00, 34.1800, 53.00, 47.00, 56.00, 7.9800, 'Bank Base Case Forecast Model', 'Forecast assumes improved cash conversion through inventory program.', 'credit_dossier.section3_customer_financial_information_historical'),
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO credit_dossier.section3a_financial_forecast (
                client_id, forecast_year, forecast_label, currency_code, unit_scale,
                sales_turnover, sales_growth_pct, gross_margin_pct, net_operating_profit,
                net_profit_before_tax_sales_pct, net_profit, ebitda, net_cash_after_operations,
                net_worth, bank_borrowing, total_liability, total_assets,
                debt_tangible_net_worth_pct, accounts_receivable_days, accounts_payable_days,
                inventory_days, interest_coverage, model_name, model_note, source_table
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (client_id, forecast_year) DO UPDATE SET
                forecast_label = EXCLUDED.forecast_label,
                currency_code = EXCLUDED.currency_code,
                unit_scale = EXCLUDED.unit_scale,
                sales_turnover = EXCLUDED.sales_turnover,
                sales_growth_pct = EXCLUDED.sales_growth_pct,
                gross_margin_pct = EXCLUDED.gross_margin_pct,
                net_operating_profit = EXCLUDED.net_operating_profit,
                net_profit_before_tax_sales_pct = EXCLUDED.net_profit_before_tax_sales_pct,
                net_profit = EXCLUDED.net_profit,
                ebitda = EXCLUDED.ebitda,
                net_cash_after_operations = EXCLUDED.net_cash_after_operations,
                net_worth = EXCLUDED.net_worth,
                bank_borrowing = EXCLUDED.bank_borrowing,
                total_liability = EXCLUDED.total_liability,
                total_assets = EXCLUDED.total_assets,
                debt_tangible_net_worth_pct = EXCLUDED.debt_tangible_net_worth_pct,
                accounts_receivable_days = EXCLUDED.accounts_receivable_days,
                accounts_payable_days = EXCLUDED.accounts_payable_days,
                inventory_days = EXCLUDED.inventory_days,
                interest_coverage = EXCLUDED.interest_coverage,
                model_name = EXCLUDED.model_name,
                model_note = EXCLUDED.model_note,
                source_table = EXCLUDED.source_table;
            """,
            rows,
        )


def seed_simple_section3_tables(conn):
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO credit_dossier.section3a_customer_facilities (
                client_id, facility_type, facility_amount_existing, utilization,
                facility_amount_new, currency_code, unit_scale, source_note
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (client_id, facility_type) DO UPDATE SET
                facility_amount_existing = EXCLUDED.facility_amount_existing,
                utilization = EXCLUDED.utilization,
                facility_amount_new = EXCLUDED.facility_amount_new,
                currency_code = EXCLUDED.currency_code,
                unit_scale = EXCLUDED.unit_scale,
                source_note = EXCLUDED.source_note;
            """,
            [
                (CLIENT_ID, 'Working Capital Revolving Credit', 18500.00, 14275.00, 22500.00, 'GBP', '000', 'Existing RCF limit proposed to increase for export receivable growth.'),
                (CLIENT_ID, 'Term Loan - CNC Expansion', 12500.00, 10840.00, 18000.00, 'GBP', '000', 'New capex tranche requested for machining line and automation cells.'),
                (CLIENT_ID, 'Bank Guarantee / LC Sublimit', 4500.00, 2210.00, 6000.00, 'GBP', '000', 'Trade facility for imported machinery components and tooling commitments.'),
            ],
        )
        cur.executemany(
            """
            INSERT INTO credit_dossier.section3a_other_financial_institution_exposure (
                client_id, exposure_type, exposure_limit, exposure, currency_code, unit_scale, source_note
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (client_id, exposure_type) DO UPDATE SET
                exposure_limit = EXCLUDED.exposure_limit,
                exposure = EXCLUDED.exposure,
                currency_code = EXCLUDED.currency_code,
                unit_scale = EXCLUDED.unit_scale,
                source_note = EXCLUDED.source_note;
            """,
            [
                (CLIENT_ID, 'Equipment Finance - Non-bank Lender', 5200.00, 3760.00, 'GBP', '000', 'Secured against two automated forging press lines.'),
                (CLIENT_ID, 'Supplier Finance Program', 3500.00, 1980.00, 'GBP', '000', 'Confirmed payables program with top steel suppliers.'),
            ],
        )
        cur.executemany(
            """
            INSERT INTO credit_dossier.section3a_collateral_guarantee_information (
                client_id, collateral_category, mitigant_type, amount, currency_code, unit_scale, source_note
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (client_id, collateral_category, mitigant_type) DO UPDATE SET
                amount = EXCLUDED.amount,
                currency_code = EXCLUDED.currency_code,
                unit_scale = EXCLUDED.unit_scale,
                source_note = EXCLUDED.source_note;
            """,
            [
                (CLIENT_ID, 'Land and Building', 'First ranking mortgage', 28600.00, 'GBP', '000', 'Independent valuation of primary manufacturing site.'),
                (CLIENT_ID, 'Plant and Machinery', 'Hypothecation', 21450.00, 'GBP', '000', 'CNC machines, forging presses and finishing equipment.'),
                (CLIENT_ID, 'Receivables and Inventory', 'Floating charge', 38400.00, 'GBP', '000', 'Eligible current assets under borrowing base.'),
                (CLIENT_ID, 'Promoter Guarantee', 'Personal guarantee', 15000.00, 'GBP', '000', 'Guarantee from managing director and promoter family trust.'),
            ],
        )
        cur.executemany(
            """
            INSERT INTO credit_dossier.section3b_documentation_security_exceptions (
                client_id, exception_code, end_date, mitigant_exception_description,
                exception_severity, status, source_note
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (client_id, exception_code) DO UPDATE SET
                end_date = EXCLUDED.end_date,
                mitigant_exception_description = EXCLUDED.mitigant_exception_description,
                exception_severity = EXCLUDED.exception_severity,
                status = EXCLUDED.status,
                source_note = EXCLUDED.source_note;
            """,
            [
                (CLIENT_ID, 'SEC-VAL-2026-01', '2026-09-30', 'Updated plant and machinery valuation to be submitted post commissioning.', 'Medium', 'Open', 'Temporary exception approved pending installation completion.'),
                (CLIENT_ID, 'DOC-INS-2026-02', '2026-08-31', 'Renewed all-risk insurance endorsement naming bank as loss payee pending.', 'Low', 'Open', 'Insurance broker confirmation received; final endorsement awaited.'),
            ],
        )
        cur.executemany(
            """
            INSERT INTO credit_dossier.section3b_covenant_description (
                client_id, covenant_type, reporting_date, due_date, description,
                threshold_value, reported_value, compliance_status, source_document,
                source_pdf_pages, source_note
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (client_id, covenant_type, reporting_date) DO UPDATE SET
                due_date = EXCLUDED.due_date,
                description = EXCLUDED.description,
                threshold_value = EXCLUDED.threshold_value,
                reported_value = EXCLUDED.reported_value,
                compliance_status = EXCLUDED.compliance_status,
                source_document = EXCLUDED.source_document,
                source_pdf_pages = EXCLUDED.source_pdf_pages,
                source_note = EXCLUDED.source_note;
            """,
            [
                (CLIENT_ID, 'Debt / Tangible Net Worth', '2025-03-31', '2025-06-30', 'Maintain total debt to tangible net worth within approved leverage ceiling.', '<= 1.25x', '0.45x', 'Compliant', SOURCE_DOCUMENT, [31], 'Based on audited FY2025 financials.'),
                (CLIENT_ID, 'Interest Coverage Ratio', '2025-03-31', '2025-06-30', 'Maintain minimum EBITDA to interest expense coverage.', '>= 4.00x', '6.89x', 'Compliant', SOURCE_DOCUMENT, [31, 32], 'Interest coverage comfortably above threshold.'),
                (CLIENT_ID, 'Receivable Aging', '2025-03-31', '2025-06-30', 'Receivables over 120 days not to exceed 10 percent of gross receivables.', '<= 10%', '4.8%', 'Compliant', SOURCE_DOCUMENT, [32], 'Receivable aging supported by customer ledger.'),
            ],
        )
        cur.executemany(
            """
            INSERT INTO credit_dossier.section3b_credit_committee_resolution (
                client_id, credit_committee_name, decision, resolution_by,
                meeting_date, meeting_no, resolution_summary,
                final_approving_authority, source_note
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (client_id, credit_committee_name, meeting_no) DO UPDATE SET
                decision = EXCLUDED.decision,
                resolution_by = EXCLUDED.resolution_by,
                meeting_date = EXCLUDED.meeting_date,
                resolution_summary = EXCLUDED.resolution_summary,
                final_approving_authority = EXCLUDED.final_approving_authority,
                source_note = EXCLUDED.source_note;
            """,
            [
                (CLIENT_ID, 'Regional Corporate Credit Committee', 'Approved with conditions', 'RCCC Secretary', '2026-05-18', 'RCCC-2026-0518-07', 'Approved renewal and enhancement subject to security perfection, insurance endorsement and quarterly covenant reporting.', 'Head of Corporate Credit - UK and Europe', 'Resolution generated from proposed Section 3 credit structure and covenant package.'),
            ],
        )


def load_section3_tables():
    ensure_database()
    with get_connection() as conn:
        create_support_clients_table(conn)
        create_section3_tables(conn)
        seed_historical_financials(conn)
        seed_forecast(conn)
        seed_simple_section3_tables(conn)
        conn.commit()


if __name__ == '__main__':
    load_section3_tables()
    print('Loaded Section 3, 3A, and 3B credit dossier tables.')
