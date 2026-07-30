DEFAULT_NARRATIVE_SECTIONS = [
    (1, 'Executive Summary', 'Overview of client, facility, and recommendation',
     'CRM, LOS, Financial summary (from financial section), ratings summary, Purpose of Loan',
     'Concise AI-generated summary with key highlights, deal rationale, and risk view'),
    (2, 'Client Overview', 'Company profile, ownership, management',
     'CRM, client website, annual report, external databases (Capital IQ, MCA filings), Company Profile, Key Customers/Suppliers, Customer Information, Ownership Structure',
     'Structured profile + narrative on business model & management quality Business overview in terms of products / services sold; Any specific on business model - example online, trading, wholesale, manufacturing, etc. Ownership profile in terms of parent company, subsidiary company, any major shareholder, etc. Country of business - basis revenue contribution, head office Any strategic or big acquisitions in last 2-3 years Key Management personnel, any changes in that High-level business segment composition Top customers / suppliers'),
    (3, 'Relationship Summary', 'Historical exposure and relationship',
     'Core Banking, RWA data, limits & utilization, Existing Loan Details, Customer Financial Information Historical, Financial Forecast, Customer Facilities, Other Financial Institution Exposure, Collateral Guarantee Information, Documentation Security Exceptions, Covenant Description, Credit Committee Resolution',
     'Summary of existing facilities, utilization trends, cross-sell opportunities Exposure in terms of Loans, or investments with the customer over the last 3 years Changes in exposure Any credit loss or delinquency reported with the customer Current balance in Deposits account by this customer Number of years customer since Key products with the Bank Data on existing limits, utilization, collateral any covenant breaches'),
    (4, 'Industry Analysis', 'Industry trends and outlook',
     'External market data, news feeds',
     'AI-generated industry overview with growth outlook and risks Mapping to a specific industry Current status of industry in terms of expected growth / performance over next 2-3 years Position of customer in this industry Key growth drivers and risks with this industry'),
    (5, 'Financial Analysis', 'Historical financial performance',
     'Uploaded FS, CRDM, Net Worth Statement, Audited Financial(3 years) Income statement, Audited Financial(3 years) balance sheet, Audited Financial(3 years) cashflow statement, Bank Statements (6-12 months), Projected Financial (Next 3 years)',
     'Automated financial tables + narrative on performance trends'),
    (6, 'Ratio Analysis', 'Key credit ratios',
     'Financial engine outputs Audited Financial(3 years) Income statement, Audited Financial(3 years) balance sheet, Audited Financial(3 years) cashflow statement, Projected Financial (Next 3 years)',
     'Ratio dashboard + commentary (e.g., leverage deterioration)'),
    (7, 'Cash Flow Analysis', 'Cash generation and debt servicing',
     'Financial statements Audited Financial(3 years) Income statement, Audited Financial(3 years) balance sheet, Audited Financial(3 years) cashflow statement, Projected Financial (Next 3 years)',
     'DSCR calculation + narrative on repayment capacity'),
    (8, 'Qualitative Assessment', 'Detailed Management Information, any pending legal cases, Macro outlook, etc.',
     'Annual Reports, company site, Industry website, Certificate of Incorporation, MOA & AOA, PAN Card, GST Registration, KYC Identity Proofs, KYC Credit Reports, KYC Income Tax Returns, Litigation Details, Declaration',
     'Qualitative summary of key management and other factors'),
    (9, 'Credit Risk Assessment', 'Risk profile of borrower',
     'Internal rating, external ratings, movement in historical ratings, Income Tax Returns 3 years, GST Returns, Litigation Details, Declaration',
     'Risk summary with key risk drivers and mitigants'),
    (10, 'Policy Mapping', "Bank's Risk Policy Coverage",
     'Existing Risk Policies of the Bank, Customer Business profile and Loan requirements',
     'Mapping of existing Risk Policies along with required controls basis loan requirements and customer business profile'),
    (11, 'Collateral & Security', 'Security coverage',
     'LOS, collateral systems, Asset Details, Property Documents',
     'Summary of collateral valuation and coverage ratios'),
    (12, 'Facility Structure', 'Loan structure and terms',
     'LOS', 'Structured description of facility terms'),
    (13, 'Covenants & Conditions', 'Financial and non-financial covenants',
     'Credit policy templates', 'Suggested covenants aligned to risk profile'),
    (14, 'ESG Analysis', 'ESG risk assessment',
     'ESG data providers', 'ESG score summary + risk commentary'),
    (15, 'Key Risks & Mitigants', 'Risk identification',
     'All modules above', 'AI-generated risk matrix with mitigants'),
    (16, 'Appendix Section', 'Supporting details',
     'All systems', 'Auto-populated data tables'),
]


def seed_narrative_sections(conn):
    """Insert the default 16 sections only for an empty database."""
    count = conn.execute('SELECT COUNT(*) FROM narrative_sections;').fetchone()[0]
    if count:
        return 0

    conn.executemany(
        """
        INSERT INTO narrative_sections (
            section_number, section_name, description, input_sources, expected_output
        ) VALUES (%s, %s, %s, %s, %s);
        """,
        DEFAULT_NARRATIVE_SECTIONS,
    )
    return len(DEFAULT_NARRATIVE_SECTIONS)
