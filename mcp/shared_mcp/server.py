import os
import re
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mistralai.client import Mistral
from psycopg import sql
from psycopg.rows import dict_row


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / 'backend' / '.env')
load_dotenv(Path(__file__).resolve().parent / '.env', override=True)

CENTRAL_DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'dbname': os.getenv('POSTGRES_DB', 'credit risk new version'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', 'root'),
}
MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY')

TABLE_NAMES = (
    'credit_dossier.credit_balance_sheet',
    'credit_dossier.credit_cashflow_statement',
    'credit_dossier.credit_income_statement',
    'credit_dossier.credit_bank_statements',
    'credit_dossier.credit_net_worth_statement',
    'credit_dossier.credit_projected_financials',
    'credit_dossier.section2_customer_information',
    'credit_dossier.section2_ownership_structure',
    'credit_dossier.section3_customer_financial_information_historical',
    'credit_dossier.section3a_financial_forecast',
    'credit_dossier.section3a_customer_facilities',
    'credit_dossier.section3a_other_financial_institution_exposure',
    'credit_dossier.section3a_collateral_guarantee_information',
    'credit_dossier.section3b_documentation_security_exceptions',
    'credit_dossier.section3b_covenant_description',
    'credit_dossier.section3b_credit_committee_resolution',
)

PDF_SPECS = (
    (1, 'Asset_Details.pdf', 'get_asset_details_content'),
    (2, 'Certificate_of_Incorporation.pdf', 'get_certificate_of_incorporation_content'),
    (3, 'Company_Profile.pdf', 'get_company_profile_content'),
    (4, 'Declarations.pdf', 'get_declarations_content'),
    (5, 'Existing_Loan_Details.pdf', 'get_existing_loan_details_content'),
    (6, 'GST_Registration.pdf', 'get_gst_registration_content'),
    (7, 'GST_Returns.pdf', 'get_gst_returns_content'),
    (8, 'Income_Tax_Returns_3_Years.pdf', 'get_income_tax_returns_3_years_content'),
    (9, 'Key_Customers_Suppliers.pdf', 'get_key_customers_suppliers_content'),
    (10, 'KYC_Credit_Reports.pdf', 'get_kyc_credit_reports_content'),
    (11, 'KYC_Identity_Proofs.pdf', 'get_kyc_identity_proofs_content'),
    (12, 'KYC_Income_Tax_Returns.pdf', 'get_kyc_income_tax_returns_content'),
    (13, 'Litigation_Details.pdf', 'get_litigation_details_content'),
    (14, 'MOA_AOA.pdf', 'get_moa_aoa_content'),
    (15, 'PAN_Card.pdf', 'get_pan_card_content'),
    (16, 'Property_Documents.pdf', 'get_property_documents_content'),
    (17, 'Purpose_of_Loan.pdf', 'get_purpose_of_loan_content'),
)

mcp = FastMCP(
    'credit_intelligence_mcp',
    instructions=(
        'Shared credit-intelligence MCP. Every tool requires client_name and uses an exact client registry match. '
        'Client databases and Mistral libraries are isolated from each other.'
    ),
    host=os.getenv('MCP_HOST', '127.0.0.1'),
    port=int(os.getenv('MCP_PORT', '8010')),
)


def client_key(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip()


def resolve_client(client_name: str) -> dict:
    normalized = client_key(client_name)
    if not normalized:
        raise ValueError('client_name is required.')
    with psycopg.connect(**CENTRAL_DB_CONFIG, row_factory=dict_row) as conn:
        row = conn.execute(
            """
            SELECT client_match, client_database, mistral_library_id, mistral_pdf_documents
            FROM mcp_client_registry
            WHERE enabled = TRUE AND LOWER(client_match) = %s
            LIMIT 1;
            """,
            (normalized,),
        ).fetchone()
    if not row or not row['client_database']:
        raise ValueError(f'No shared MCP data is configured for client "{client_name}".')
    return dict(row)


def split_table_name(table_name: str) -> tuple[str, str]:
    schema_name, _, bare_table_name = table_name.partition('.')
    return (schema_name, bare_table_name) if bare_table_name else ('public', schema_name)


def validate_table_name(table_name: str):
    if table_name not in TABLE_NAMES:
        raise ValueError('Unknown credit intelligence table.')


@mcp.tool()
def get_mistral_library_id(client_name: str) -> str:
    """Return the Mistral PDF library ID configured for one exact client."""
    return resolve_client(client_name)['mistral_library_id'] or ''


@mcp.tool()
def list_credit_tables(client_name: str) -> list[str]:
    """List the credit intelligence tables available to one exact client."""
    resolve_client(client_name)
    return list(TABLE_NAMES)


@mcp.tool()
def describe_credit_table(client_name: str, table_name: str) -> dict:
    """Return columns and row count for one client's credit intelligence table."""
    validate_table_name(table_name)
    client = resolve_client(client_name)
    schema_name, bare_table_name = split_table_name(table_name)
    with psycopg.connect(**{**CENTRAL_DB_CONFIG, 'dbname': client['client_database']}, row_factory=dict_row) as conn:
        columns = conn.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position;""",
            (schema_name, bare_table_name),
        ).fetchall()
        count = conn.execute(
            sql.SQL('SELECT COUNT(*) AS count FROM {};').format(
                sql.Identifier(schema_name, bare_table_name)
            )
        ).fetchone()['count']
    return {'table': table_name, 'columns': [row['column_name'] for row in columns], 'rowCount': count}


@mcp.tool()
def fetch_credit_table_rows(client_name: str, table_name: str, limit: int = 20) -> list[dict]:
    """Fetch rows from one client's credit intelligence table only."""
    validate_table_name(table_name)
    client = resolve_client(client_name)
    schema_name, bare_table_name = split_table_name(table_name)
    safe_limit = max(1, min(limit, 100))
    with psycopg.connect(**{**CENTRAL_DB_CONFIG, 'dbname': client['client_database']}, row_factory=dict_row) as conn:
        rows = conn.execute(
            sql.SQL('SELECT * FROM {} LIMIT {};').format(
                sql.Identifier(schema_name, bare_table_name), sql.Literal(safe_limit)
            )
        ).fetchall()
    return [dict(row) for row in rows]


@mcp.tool()
def list_mistral_pdf_tools(client_name: str) -> list[dict]:
    """List the 17 PDF tools available to one exact client."""
    client = resolve_client(client_name)
    documents = {document.get('tool_name'): document for document in client['mistral_pdf_documents'] or []}
    return [
        {
            'number': number,
            'name': name,
            'toolName': tool_name,
            'documentId': documents.get(tool_name, {}).get('document_id'),
            'libraryId': client['mistral_library_id'],
        }
        for number, name, tool_name in PDF_SPECS
    ]


def fetch_pdf(client_name: str, tool_name: str, page_start: int | None, page_end: int | None) -> dict:
    client = resolve_client(client_name)
    document = next(
        (item for item in client['mistral_pdf_documents'] or [] if item.get('tool_name') == tool_name), None
    )
    if not document or not client['mistral_library_id']:
        raise ValueError(f'PDF source "{tool_name}" is not available for client "{client_name}".')
    if not MISTRAL_API_KEY:
        raise ValueError('MISTRAL_API_KEY is not configured for the shared MCP server.')
    kwargs = {'library_id': client['mistral_library_id'], 'document_id': document['document_id']}
    if page_start is not None:
        kwargs['page_start'] = page_start
    if page_end is not None:
        kwargs['page_end'] = page_end
    response = Mistral(api_key=MISTRAL_API_KEY).beta.libraries.documents.text_content(**kwargs)
    data = response.model_dump() if hasattr(response, 'model_dump') else response.__dict__
    return {
        'number': document.get('number'), 'name': document.get('name'),
        'documentId': document.get('document_id'), 'libraryId': client['mistral_library_id'],
        'pageStart': page_start, 'pageEnd': page_end, 'text': data.get('text', ''),
    }


def register_pdf_tool(number: int, name: str, tool_name: str):
    @mcp.tool(name=tool_name, description=f'Return extracted text from {name} for one exact client.')
    def pdf_content(client_name: str, page_start: int | None = None, page_end: int | None = None) -> dict:
        return fetch_pdf(client_name, tool_name, page_start, page_end)


for pdf_spec in PDF_SPECS:
    register_pdf_tool(*pdf_spec)


if __name__ == '__main__':
    mcp.run(transport='streamable-http')
