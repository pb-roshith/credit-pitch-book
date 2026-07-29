import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mistralai.client import Mistral
from psycopg import sql
from psycopg.rows import dict_row

from database import get_connection
from mistral_pdf_config import MISTRAL_PDF_DOCUMENTS
from table_config import ALL_TABLES


load_dotenv()

MISTRAL_LIBRARY_ID = os.getenv('MISTRAL_LIBRARY_ID', '019f561a-b2e6-7552-b9fe-1215aec0f20c')
MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY')
TABLE_NAMES = ALL_TABLES


mcp = FastMCP(
    'intel_mcp',
    instructions=(
        'Local MCP server for credit intelligence tables loaded from Excel files. '
        f'Mistral library id: {MISTRAL_LIBRARY_ID}.'
    ),
    host=os.getenv('MCP_HOST', '127.0.0.1'),
    port=int(os.getenv('MCP_PORT', '8010')),
)


def validate_table_name(table_name):
    if table_name not in TABLE_NAMES:
        allowed = ', '.join(TABLE_NAMES)
        raise ValueError(f'Unknown table: {table_name}. Allowed tables: {allowed}')


def split_table_name(table_name):
    parts = table_name.split('.', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return 'public', table_name


@mcp.tool()
def get_mistral_library_id() -> str:
    """Return the configured Mistral library id for the PDF knowledge library."""
    return MISTRAL_LIBRARY_ID


@mcp.tool()
def list_credit_tables() -> list[str]:
    """List the credit intelligence PostgreSQL tables."""
    return list(TABLE_NAMES)


@mcp.tool()
def describe_credit_table(table_name: str) -> dict:
    """Return column names and row count for one credit intelligence table."""
    validate_table_name(table_name)
    schema_name, bare_table_name = split_table_name(table_name)
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position;
                """,
                (schema_name, bare_table_name),
            )
            columns = [row['column_name'] for row in cur.fetchall()]
            cur.execute(
                sql.SQL('SELECT COUNT(*) AS count FROM {};').format(
                    sql.Identifier(schema_name, bare_table_name),
                )
            )
            count = cur.fetchone()['count']
    return {'table': table_name, 'columns': columns, 'rowCount': count}


@mcp.tool()
def fetch_credit_table_rows(table_name: str, limit: int = 20) -> list[dict]:
    """Fetch rows from one credit intelligence table."""
    validate_table_name(table_name)
    schema_name, bare_table_name = split_table_name(table_name)
    safe_limit = max(1, min(limit, 100))
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                sql.SQL('SELECT * FROM {} LIMIT {};').format(
                    sql.Identifier(schema_name, bare_table_name),
                    sql.Literal(safe_limit),
                )
            )
            return [dict(row) for row in cur.fetchall()]


@mcp.tool()
def list_mistral_pdf_tools() -> list[dict]:
    """List the 17 Mistral PDF tools and the file each tool reads."""
    return [
        {
            'number': document['number'],
            'name': document['name'],
            'documentId': document['document_id'],
            'toolName': document['tool_name'],
            'libraryId': MISTRAL_LIBRARY_ID,
        }
        for document in MISTRAL_PDF_DOCUMENTS
    ]


def get_mistral_client():
    if not MISTRAL_API_KEY:
        raise ValueError('MISTRAL_API_KEY is not configured in intel_mcp/.env')
    return Mistral(api_key=MISTRAL_API_KEY)


def fetch_mistral_pdf_content(document: dict, page_start: int | None = None, page_end: int | None = None) -> dict:
    client = get_mistral_client()
    kwargs = {
        'library_id': MISTRAL_LIBRARY_ID,
        'document_id': document['document_id'],
    }
    if page_start is not None:
        kwargs['page_start'] = page_start
    if page_end is not None:
        kwargs['page_end'] = page_end

    response = client.beta.libraries.documents.text_content(**kwargs)
    data = response.model_dump() if hasattr(response, 'model_dump') else response.__dict__
    return {
        'number': document['number'],
        'name': document['name'],
        'documentId': document['document_id'],
        'libraryId': MISTRAL_LIBRARY_ID,
        'pageStart': page_start,
        'pageEnd': page_end,
        'text': data.get('text', ''),
    }


def register_pdf_tool(document: dict):
    @mcp.tool(
        name=document['tool_name'],
        description=f'Return extracted text content from {document["name"]} in the Mistral PDF library.',
    )
    def pdf_content(page_start: int | None = None, page_end: int | None = None) -> dict:
        return fetch_mistral_pdf_content(document, page_start=page_start, page_end=page_end)


for pdf_document in MISTRAL_PDF_DOCUMENTS:
    register_pdf_tool(pdf_document)


if __name__ == '__main__':
    mcp.run(transport='streamable-http')
