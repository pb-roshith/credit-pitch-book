import ast
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from random import Random
from xml.sax.saxutils import escape

import psycopg
from dotenv import dotenv_values
from mistralai.client import Mistral
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from financial_table_schema import FINANCIAL_TABLE_NAMES, FINANCIAL_TABLES

ROOT_DIR = Path(__file__).resolve().parents[1]
MCP_ROOT = ROOT_DIR / 'mcp'
MCP_TEMPLATE_DIR = MCP_ROOT / 'client_template'
SHARED_MCP_DIR = MCP_ROOT / 'shared_mcp'
LEGACY_SOURCE_MCP_DIR = MCP_ROOT / 'intel_mcp'

PDF_FILES = [
    'Asset_Details.pdf',
    'Certificate_of_Incorporation.pdf',
    'Company_Profile.pdf',
    'Declarations.pdf',
    'Existing_Loan_Details.pdf',
    'GST_Registration.pdf',
    'GST_Returns.pdf',
    'Income_Tax_Returns_3_Years.pdf',
    'Key_Customers_Suppliers.pdf',
    'KYC_Credit_Reports.pdf',
    'KYC_Identity_Proofs.pdf',
    'KYC_Income_Tax_Returns.pdf',
    'Litigation_Details.pdf',
    'MOA_AOA.pdf',
    'PAN_Card.pdf',
    'Property_Documents.pdf',
    'Purpose_of_Loan.pdf',
]

EXCEL_TABLE_NAMES = FINANCIAL_TABLE_NAMES
SECTION2_TABLE_NAMES = (
    'credit_dossier.section2_customer_information',
    'credit_dossier.section2_ownership_structure',
)
SECTION3_TABLE_NAMES = (
    'credit_dossier.section3_customer_financial_information_historical',
    'credit_dossier.section3a_financial_forecast',
    'credit_dossier.section3a_customer_facilities',
    'credit_dossier.section3a_other_financial_institution_exposure',
    'credit_dossier.section3a_collateral_guarantee_information',
    'credit_dossier.section3b_documentation_security_exceptions',
    'credit_dossier.section3b_covenant_description',
    'credit_dossier.section3b_credit_committee_resolution',
)
ALL_CLIENT_TABLE_NAMES = EXCEL_TABLE_NAMES + SECTION2_TABLE_NAMES + SECTION3_TABLE_NAMES


def slugify(value):
    slug = re.sub(r'[^a-z0-9]+', '_', value.lower()).strip('_')
    return slug or 'client'


def db_name_for_client(client_name):
    return f'{slugify(client_name)}_mcp_db'


def ensure_mcp_template():
    """Keep a generic MCP template separate from any real client folder."""
    if MCP_TEMPLATE_DIR.exists():
        return MCP_TEMPLATE_DIR
    if not LEGACY_SOURCE_MCP_DIR.exists():
        raise FileNotFoundError('MCP client template is missing.')
    shutil.copytree(
        LEGACY_SOURCE_MCP_DIR,
        MCP_TEMPLATE_DIR,
        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.env', 'mistral_pdf_config.py'),
    )
    return MCP_TEMPLATE_DIR


def load_mcp_document_config(client_slug):
    config_path = MCP_ROOT / f'{client_slug}_mcp' / 'mistral_pdf_config.py'
    if not config_path.exists():
        return []
    try:
        module = ast.parse(config_path.read_text(encoding='utf-8'))
        assignment = next(
            node for node in module.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == 'MISTRAL_PDF_DOCUMENTS' for target in node.targets)
        )
        documents = ast.literal_eval(assignment.value)
        return documents if isinstance(documents, list) else []
    except (OSError, SyntaxError, ValueError, StopIteration):
        return []


def load_existing_mistral_assets(client_slug):
    # The shared registry is the source of truth. This folder fallback supports
    # migration from the former per-client MCP layout.
    try:
        from database import get_connection

        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT mistral_library_id, mistral_pdf_documents
                FROM mcp_client_registry
                WHERE client_match = %s;
                """,
                (client_slug.replace('_', ' '),),
            ).fetchone()
            if row and row[0]:
                return row[0], row[1] or []
    except Exception:
        pass

    values = dotenv_values(MCP_ROOT / f'{client_slug}_mcp' / '.env')
    library_id = values.get('MISTRAL_LIBRARY_ID') or None
    documents = load_mcp_document_config(client_slug)
    return library_id, documents


def missing_document_names(documents):
    available = {
        document.get('name')
        for document in documents
        if isinstance(document, dict) and document.get('name') and document.get('document_id')
    }
    return [filename for filename in PDF_FILES if filename not in available]


def existing_or_new_context(client_slug, client_name, industry, geography):
    has_existing_output = (MCP_ROOT / f'{client_slug}_mcp').exists()
    if not has_existing_output:
        try:
            with psycopg.connect(**get_base_db_config('postgres')) as conn:
                has_existing_output = conn.execute(
                    'SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = %s);',
                    (db_name_for_client(client_name),),
                ).fetchone()[0]
        except Exception:
            pass
    return build_context(client_name, industry, geography) if has_existing_output else generate_context_with_agent(client_name, industry, geography)


def mcp_needs_refresh(client_slug, dbname, library_id, documents):
    target = MCP_ROOT / f'{client_slug}_mcp'
    if not target.exists():
        return True

    values = dotenv_values(target / '.env')
    if values.get('INTEL_MCP_DB') != dbname or values.get('MISTRAL_LIBRARY_ID', '') != (library_id or ''):
        return True

    current_documents = load_mcp_document_config(client_slug)
    current_ids = {
        document.get('name'): document.get('document_id')
        for document in current_documents
        if isinstance(document, dict)
    }
    expected_ids = {
        document.get('name'): document.get('document_id')
        for document in documents
        if isinstance(document, dict)
    }
    return current_ids != expected_ids


def choose_mcp_port():
    used_ports = set()
    for env_path in MCP_ROOT.glob('*_mcp/.env'):
        values = dotenv_values(env_path)
        try:
            used_ports.add(int(values.get('MCP_PORT', '0')))
        except ValueError:
            pass
    port = 8100
    while port in used_ports:
        port += 1
    return port


def existing_mcp_port(client_slug):
    env_path = MCP_ROOT / f'{client_slug}_mcp' / '.env'
    if not env_path.exists():
        return None
    try:
        return int(dotenv_values(env_path).get('MCP_PORT', ''))
    except ValueError:
        return None


def is_mcp_port_open(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.4):
            return True
    except OSError:
        return False


def stop_mcp_server(port):
    if os.name != 'nt' or not is_mcp_port_open(port):
        return False

    result = subprocess.run(
        ['netstat', '-ano'],
        capture_output=True,
        text=True,
        check=False,
    )
    port_suffix = f':{port}'
    for line in result.stdout.splitlines():
        columns = line.split()
        if len(columns) < 5 or columns[3] != 'LISTENING' or not columns[1].endswith(port_suffix):
            continue
        subprocess.run(['taskkill', '/PID', columns[-1], '/F'], capture_output=True, check=False)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if not is_mcp_port_open(port):
                return True
            time.sleep(0.15)
    return not is_mcp_port_open(port)


def start_client_mcp(mcp_folder, port):
    if is_mcp_port_open(port):
        return {'started': False, 'ready': True, 'message': 'MCP server is already running.'}

    popen_options = {
        'cwd': str(mcp_folder),
        'stdin': subprocess.DEVNULL,
        'stdout': subprocess.DEVNULL,
        'stderr': subprocess.DEVNULL,
    }
    if os.name == 'nt':
        popen_options['creationflags'] = subprocess.CREATE_NO_WINDOW

    try:
        subprocess.Popen([sys.executable, 'server.py'], **popen_options)
    except OSError as exc:
        return {'started': False, 'ready': False, 'message': f'Unable to start MCP server: {exc}'}

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if is_mcp_port_open(port):
            return {'started': True, 'ready': True, 'message': 'MCP server started and is ready.'}
        time.sleep(0.25)

    return {
        'started': True,
        'ready': False,
        'message': 'MCP process was started but did not become ready within 15 seconds.',
    }


def get_base_db_config(dbname='postgres'):
    env = dotenv_values(ensure_mcp_template() / '.env')
    return {
        'host': env.get('POSTGRES_HOST') or os.getenv('POSTGRES_HOST', 'localhost'),
        'port': env.get('POSTGRES_PORT') or os.getenv('POSTGRES_PORT', '5432'),
        'dbname': dbname,
        'user': env.get('POSTGRES_USER') or os.getenv('POSTGRES_USER', 'postgres'),
        'password': env.get('POSTGRES_PASSWORD') or os.getenv('POSTGRES_PASSWORD', 'root'),
    }


def ensure_database(dbname):
    with psycopg.connect(**get_base_db_config('postgres'), autocommit=True) as conn:
        row = conn.execute('SELECT 1 FROM pg_database WHERE datname = %s;', (dbname,)).fetchone()
        if not row:
            conn.execute(f'CREATE DATABASE "{dbname}"')


def build_context(client_name, industry, geography):
    rng = Random(f'{client_name}|{industry}|{geography}')
    revenue = rng.randint(75000, 165000)
    return {
        'client_name': client_name,
        'industry': industry,
        'geography': geography,
        'registered_address': f'Plot {rng.randint(10, 99)}, Industrial Estate, {geography}',
        'incorporation_year': rng.randint(2008, 2020),
        'pan': f'ABCDE{rng.randint(1000, 9999)}F',
        'gstin': f'27ABCDE{rng.randint(1000, 9999)}F1Z{rng.randint(1, 9)}',
        'cin': f'U{rng.randint(10000, 99999)}MH{rng.randint(2008, 2020)}PTC{rng.randint(100000, 999999)}',
        'requested_limit': rng.choice([750, 1000, 1250, 1500, 1800]),
        'revenue': revenue,
        'ebitda': round(revenue * rng.uniform(0.12, 0.19), 2),
        'net_worth': round(revenue * rng.uniform(0.32, 0.48), 2),
        'customers': ['Tata Motors Limited', 'Mahindra & Mahindra Limited', 'Bharat Forge Limited', 'Cummins India Limited'],
        'suppliers': ['JSW Steel Limited', 'Tata Steel Limited', 'Hindalco Industries Limited', 'Bharat Petroleum Corporation'],
        'directors': ['Ananya Rao', 'Rohan Mehta', 'Meera Shah'],
        'generated_document_summaries': [],
        'created_at': datetime.now().isoformat(timespec='seconds'),
    }


def get_mistral_api_key():
    return (
        os.getenv('MISTRAL_API_KEY')
        or dotenv_values(ROOT_DIR / 'backend' / '.env').get('MISTRAL_API_KEY')
        or dotenv_values(ensure_mcp_template() / '.env').get('MISTRAL_API_KEY')
    )


def extract_conversation_text(response):
    fragments = []
    for output in getattr(response, 'outputs', []) or []:
        if getattr(output, 'type', None) != 'message.output':
            continue
        content = getattr(output, 'content', '')
        if isinstance(content, str):
            fragments.append(content)
        else:
            fragments.append(''.join(getattr(item, 'text', '') for item in content))
    return '\n'.join(fragments).strip()


def beta_agent_json(prompt, fallback, max_tokens=5200, temperature=0.3):
    api_key = get_mistral_api_key()
    if not api_key:
        return fallback

    try:
        client = Mistral(api_key=api_key)
        agent = client.beta.agents.create(
            model=os.getenv('MISTRAL_GENERATION_MODEL', 'mistral-large-latest'),
            name='Manufactured Credit Data Generator',
            instructions='Return valid JSON only. Do not include markdown, comments, or prose outside JSON.',
            completion_args={
                'temperature': temperature,
                'max_tokens': max_tokens,
                'response_format': {'type': 'json_object'},
            },
        )
        response = client.beta.conversations.start(agent_id=agent.id, inputs=prompt, store=False)
        data = json.loads(extract_conversation_text(response))
        return data if isinstance(data, type(fallback)) else fallback
    except Exception:
        return fallback


def generate_context_with_agent(client_name, industry, geography):
    fallback = build_context(client_name, industry, geography)
    prompt = json.dumps(
        {
            'task': 'Create one realistic internally consistent borrower master context for a credit dossier data pack.',
            'clientName': client_name,
            'industry': industry,
            'geography': geography,
            'requiredKeys': list(fallback.keys()),
            'rules': [
                'Use the same identifiers across all generated PDFs and tables.',
                'Include realistic directors, customers, suppliers, financial values, facilities and collateral.',
                'Use numeric values in GBP thousands where possible.',
            ],
            'fallbackExample': fallback,
        }
    )
    data = beta_agent_json(prompt, fallback, max_tokens=2600, temperature=0.25)
    return {**fallback, **data, 'created_at': fallback['created_at'], 'generated_document_summaries': []}


def compact_context(context):
    return {key: value for key, value in context.items() if key != 'generated_document_summaries'}


def remember_document(context, filename, summary):
    summaries = context.setdefault('generated_document_summaries', [])
    summaries.append({'filename': filename, 'summary': str(summary)[:900]})
    if len(summaries) > 10:
        del summaries[:-10]


def previous_document_context(context):
    summaries = context.get('generated_document_summaries') or []
    if not summaries:
        return 'No previous documents generated yet.'
    return json.dumps(summaries, ensure_ascii=True)


def fallback_pdf_document(filename, context):
    return {
        'title': filename.replace('_', ' ').replace('.pdf', ''),
        'document_summary': f'{filename} manufactured for {context["client_name"]}.',
        'sections': [
            {
                'heading': 'Borrower Reference',
                'paragraphs': [
                    f'{context["client_name"]} operates in {context["industry"]} across {context["geography"]}.',
                    f'This document uses the common manufactured borrower context created at {context["created_at"]}.',
                ],
                'table': [
                    ['Field', 'Value'],
                    ['PAN', context['pan']],
                    ['GSTIN', context['gstin']],
                    ['CIN', context['cin']],
                    ['Requested Limit', f"{context['requested_limit']} lakh"],
                ],
            },
            {
                'heading': 'Credit Relevance',
                'paragraphs': [
                    f'The data supports credit assessment, source discovery and narrative drafting for {context["client_name"]}.',
                    'Generated values are internally aligned with the other PDFs and database tables in this MCP data pack.',
                ],
                'table': [],
            },
        ],
    }


def generate_pdf_document(filename, context):
    fallback = fallback_pdf_document(filename, context)
    prompt = json.dumps(
        {
            'task': f'Generate full realistic content for credit PDF file {filename}.',
            'clientContext': compact_context(context),
            'previousGeneratedDocuments': previous_document_context(context),
            'requiredShape': {
                'title': 'Human readable title',
                'document_summary': 'Concise summary',
                'sections': [
                    {
                        'heading': 'Section heading',
                        'paragraphs': ['paragraph text'],
                        'table': [['Column 1', 'Column 2'], ['Row value', 'Row value']],
                    }
                ],
            },
            'rules': [
                'Create 5 to 8 sections specific to this PDF.',
                'Use only the provided client context and keep identifiers consistent.',
                'Use previousGeneratedDocuments to avoid contradictions and maintain continuity.',
                'Do not use placeholders or generic filler.',
            ],
        }
    )
    document = beta_agent_json(prompt, fallback, max_tokens=5200, temperature=0.32)
    if not document.get('sections'):
        return fallback
    return document


def styled_table(rows):
    table = Table(rows, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#003A8C')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#9AA6B2')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def write_pdf(path, filename, context):
    document = generate_pdf_document(filename, context)
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(escape(str(document.get('title') or filename)), styles['Title']),
        Paragraph(escape(str(context['client_name'])), styles['Heading2']),
        Paragraph(escape(f"Prepared on {context['created_at']}"), styles['Normal']),
        Spacer(1, 12),
    ]
    for section in document.get('sections', []):
        heading = section.get('heading')
        if heading:
            story.append(Paragraph(escape(str(heading)), styles['Heading2']))
            story.append(Spacer(1, 6))
        for paragraph in section.get('paragraphs') or []:
            story.append(Paragraph(escape(str(paragraph)), styles['BodyText']))
            story.append(Spacer(1, 7))
        rows = section.get('table') or []
        if rows and isinstance(rows, list) and all(isinstance(row, list) for row in rows):
            story.append(styled_table([[escape(str(cell)) for cell in row] for row in rows]))
            story.append(Spacer(1, 8))
    doc.build(story)
    remember_document(context, filename, document.get('document_summary', 'Generated PDF document.'))


def create_pdfs(output_dir, context, filenames=None):
    docs_dir = Path(output_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for filename in PDF_FILES if filenames is None else filenames:
        path = docs_dir / filename
        write_pdf(path, filename, context)
        paths.append(path)
    return paths


def create_mistral_library_and_upload(context, pdf_paths, library_id=None, existing_documents=None):
    api_key = os.getenv('MISTRAL_API_KEY') or dotenv_values(ensure_mcp_template() / '.env').get('MISTRAL_API_KEY')
    if not api_key:
        return library_id, existing_documents or [], []

    client = Mistral(api_key=api_key)
    if not library_id:
        library = client.beta.libraries.create(
            name=f'{context["client_name"]} MCP Library',
            description=f'Synthetic manufactured credit documents for {context["client_name"]}.',
        )
        library_id = library.id

    documents_by_name = {
        document['name']: document
        for document in existing_documents or []
        if isinstance(document, dict) and document.get('name') and document.get('document_id')
    }
    uploaded_names = []
    for path in pdf_paths:
        if path.name in documents_by_name:
            continue
        with path.open('rb') as handle:
            document = client.beta.libraries.documents.upload(
                library_id=library_id,
                file={'file_name': path.name, 'content': handle, 'content_type': 'application/pdf'},
            )
        documents_by_name[path.name] = {
            'number': PDF_FILES.index(path.name) + 1,
            'document_id': document.id,
            'name': path.name,
            'tool_name': f'get_{path.stem.lower()}_content',
        }
        uploaded_names.append(path.name)
    documents = [documents_by_name[filename] for filename in PDF_FILES if filename in documents_by_name]
    return library_id, documents, uploaded_names


def generate_rows_for_table(table_name, columns, fallback_rows, context):
    fallback = fallback_rows[:25] if fallback_rows else []
    prompt = json.dumps(
        {
            'task': f'Generate realistic rows for PostgreSQL table {table_name}.',
            'clientContext': compact_context(context),
            'columns': columns,
            'fallbackRowsExample': fallback[:6],
            'requiredShape': {'rows': [['value for each column']]},
            'rules': [
                'Return JSON object with key rows only.',
                'Rows must be rectangular and each row must have exactly the same number of values as columns.',
                'Generate realistic financial/credit data consistent with the clientContext.',
                'Do not use placeholders.',
            ],
        }
    )
    data = beta_agent_json(prompt, {'rows': fallback}, max_tokens=4200, temperature=0.24)
    rows = data.get('rows') if isinstance(data, dict) else None
    if not rows or not isinstance(rows, list):
        return fallback_rows

    cleaned = []
    for row in rows:
        if not isinstance(row, list):
            continue
        normalized = [None if value == '' else str(value) for value in row[: len(columns)]]
        normalized += [None] * (len(columns) - len(normalized))
        if any(value is not None for value in normalized):
            cleaned.append(normalized)
    return cleaned or fallback_rows


def contextualize_seeded_tables(conn, context, seeded_tables):
    current_year = datetime.now().year
    client_id = 1001
    seeded_tables = set(seeded_tables)
    if 'credit_dossier.section2_customer_information' in seeded_tables:
        conn.execute(
            """
            UPDATE credit_dossier.section2_customer_information
            SET business_activities = %s,
                business_since = %s,
                source_document = %s
            WHERE client_id = %s;
            """,
            (
                f"{context['industry']} operations serving customers across {context['geography']} with manufactured synthetic credit records.",
                str(context.get('incorporation_year', current_year - 8)),
                f"Manufactured data pack for {context['client_name']}",
                client_id,
            ),
        )
    if 'credit_dossier.section2_ownership_structure' in seeded_tables:
        conn.execute(
            """
            UPDATE credit_dossier.section2_ownership_structure
            SET owner_details = %s,
                source_document = %s
            WHERE client_id = %s AND ownership_id = (
                SELECT ownership_id FROM credit_dossier.section2_ownership_structure WHERE client_id = %s ORDER BY ownership_id LIMIT 1
            );
            """,
            (
                f"{context['client_name']} Promoter Group",
                f"Manufactured ownership records for {context['client_name']}",
                client_id,
                client_id,
            ),
        )
    if 'credit_dossier.section3_customer_financial_information_historical' not in seeded_tables:
        return
    historical_rows = [
        (
            client_id,
            current_year - 3 + idx,
            f'{current_year - 3 + idx}-03-31',
            12,
            'Audited',
            'Synthetic & Co. Chartered Accountants',
            'GBP',
            '000',
            round(float(context['revenue']) * (0.78 + idx * 0.11), 2),
            round(8.0 + idx * 3.2, 4),
            round(30.5 + idx * 0.9, 4),
            round(float(context['ebitda']) * (0.62 + idx * 0.12), 2),
            round(7.8 + idx * 0.8, 4),
            round(float(context['ebitda']) * (0.42 + idx * 0.08), 2),
            round(float(context['ebitda']) * (0.70 + idx * 0.14), 2),
            round(float(context['ebitda']) * (0.55 + idx * 0.12), 2),
            round(float(context['net_worth']) * (0.78 + idx * 0.11), 2),
            round(float(context['requested_limit']) * (10 + idx * 1.4), 2),
            round(float(context['revenue']) * (0.42 + idx * 0.03), 2),
            round(float(context['revenue']) * (0.72 + idx * 0.08), 2),
            round(58 - idx * 2.5, 4),
            round(62 - idx * 2.0, 2),
            round(52 - idx * 1.5, 2),
            round(66 - idx * 2.0, 2),
            round(5.6 + idx * 0.55, 4),
            f"Manufactured financial statements for {context['client_name']}",
            [20 + idx],
            'Generated from shared manufactured borrower context.',
        )
        for idx in range(3)
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
                sales_turnover = EXCLUDED.sales_turnover,
                net_profit = EXCLUDED.net_profit,
                ebitda = EXCLUDED.ebitda,
                net_worth = EXCLUDED.net_worth,
                bank_borrowing = EXCLUDED.bank_borrowing,
                source_document = EXCLUDED.source_document,
                data_quality_note = EXCLUDED.data_quality_note;
            """,
            historical_rows,
        )


def copy_client_mcp_folder(client_slug, dbname, library_id, documents, port):
    MCP_ROOT.mkdir(exist_ok=True)
    target = MCP_ROOT / f'{client_slug}_mcp'
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        ensure_mcp_template(),
        target,
        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'),
    )

    source_env = dotenv_values(ensure_mcp_template() / '.env')
    env_lines = []
    for key in ['POSTGRES_HOST', 'POSTGRES_PORT', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'MISTRAL_API_KEY']:
        value = source_env.get(key) or os.getenv(key)
        if value:
            env_lines.append(f'{key}={value}')
    env_lines.extend(
        [
            f'INTEL_MCP_DB={dbname}',
            f'MISTRAL_LIBRARY_ID={library_id or ""}',
            'MCP_HOST=127.0.0.1',
            f'MCP_PORT={port}',
        ]
    )
    (target / '.env').write_text('\n'.join(env_lines) + '\n', encoding='utf-8')

    if documents:
        config = 'MISTRAL_PDF_DOCUMENTS = ' + repr(documents) + '\n'
        (target / 'mistral_pdf_config.py').write_text(config, encoding='utf-8')

    return target


def register_backend_mcp(client_name, dbname, library_id, documents):
    from database import get_connection

    shared_url = os.getenv('SHARED_MCP_URL', 'http://127.0.0.1:8010/mcp')
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO mcp_client_registry (
                client_match, mcp_url, client_database, mistral_library_id, mistral_pdf_documents, enabled
            )
            VALUES (%s, %s, %s, %s, %s::jsonb, TRUE)
            ON CONFLICT (client_match) DO UPDATE SET
                mcp_url = EXCLUDED.mcp_url,
                client_database = EXCLUDED.client_database,
                mistral_library_id = EXCLUDED.mistral_library_id,
                mistral_pdf_documents = EXCLUDED.mistral_pdf_documents,
                enabled = TRUE,
                updated_at = NOW();
            """,
            (
                slugify(client_name).replace('_', ' '), shared_url, dbname, library_id,
                json.dumps(documents),
            ),
        )
        conn.commit()


def start_shared_mcp():
    return start_client_mcp(SHARED_MCP_DIR, int(os.getenv('SHARED_MCP_PORT', '8010')))


def split_qualified_table_name(table_name):
    return table_name.split('.', 1)


def create_financial_table(conn, table_name, columns):
    schema_name, bare_table_name = split_qualified_table_name(table_name)
    conn.execute(psycopg.sql.SQL('CREATE SCHEMA IF NOT EXISTS {};').format(psycopg.sql.Identifier(schema_name)))
    column_definitions = [psycopg.sql.SQL('{} TEXT').format(psycopg.sql.Identifier(column)) for column in columns]
    conn.execute(psycopg.sql.SQL('DROP TABLE IF EXISTS {};').format(psycopg.sql.Identifier(schema_name, bare_table_name)))
    conn.execute(
        psycopg.sql.SQL('CREATE TABLE {} ({})').format(
            psycopg.sql.Identifier(schema_name, bare_table_name),
            psycopg.sql.SQL(', ').join(column_definitions),
        )
    )


def insert_financial_rows(conn, table_name, columns, rows):
    if not rows:
        return
    schema_name, bare_table_name = split_qualified_table_name(table_name)
    query = psycopg.sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
        psycopg.sql.Identifier(schema_name, bare_table_name),
        psycopg.sql.SQL(', ').join(psycopg.sql.Identifier(column) for column in columns),
        psycopg.sql.SQL(', ').join(psycopg.sql.Placeholder() for _ in columns),
    )
    with conn.cursor() as cur:
        cur.executemany(query, rows)


def missing_client_tables(dbname):
    missing = []
    with psycopg.connect(**get_base_db_config(dbname)) as conn:
        with conn.cursor() as cur:
            for table_name in ALL_CLIENT_TABLE_NAMES:
                schema_name, bare_table_name = split_qualified_table_name(table_name)
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = %s AND table_name = %s
                    );
                    """,
                    (schema_name, bare_table_name),
                )
                if not cur.fetchone()[0]:
                    missing.append(table_name)
                    continue
                cur.execute(
                    psycopg.sql.SQL('SELECT EXISTS (SELECT 1 FROM {});').format(
                        psycopg.sql.Identifier(schema_name, bare_table_name),
                    )
                )
                if not cur.fetchone()[0]:
                    missing.append(table_name)
    return missing


def seed_tables(dbname, context, missing_tables):
    missing_tables = set(missing_tables)
    if not missing_tables:
        return

    import sys

    intel_path = str(ensure_mcp_template())
    shadowed_modules = [
        'database',
        'load_section2_tables',
        'load_section3_tables',
    ]
    saved_modules = {name: sys.modules.get(name) for name in shadowed_modules}
    for name in shadowed_modules:
        sys.modules.pop(name, None)
    sys.path.insert(0, intel_path)
    try:
        from database import get_connection
        from load_section2_tables import create_section2_tables, create_support_clients_table, seed_customer_information, seed_ownership_structure
        from load_section3_tables import create_section3_tables, seed_forecast, seed_historical_financials, seed_simple_section3_tables

        with get_connection(dbname) as conn:
            create_support_clients_table(conn)
            conn.execute(
                """
                UPDATE credit_dossier.clients
                SET client_name = %s
                WHERE client_id = 1001;
                """,
                (context['client_name'],),
            )
            for table_name in FINANCIAL_TABLE_NAMES:
                if table_name not in missing_tables:
                    continue
                schema = FINANCIAL_TABLES[table_name]
                columns = schema['columns']
                rows = generate_rows_for_table(table_name, columns, schema['fallbackRows'], context)
                create_financial_table(conn, table_name, columns)
                insert_financial_rows(conn, table_name, columns, rows)
            if missing_tables.intersection(SECTION2_TABLE_NAMES):
                create_section2_tables(conn)
                if 'credit_dossier.section2_customer_information' in missing_tables:
                    seed_customer_information(conn)
                if 'credit_dossier.section2_ownership_structure' in missing_tables:
                    seed_ownership_structure(conn)
            if missing_tables.intersection(SECTION3_TABLE_NAMES):
                create_section3_tables(conn)
                if 'credit_dossier.section3_customer_financial_information_historical' in missing_tables:
                    seed_historical_financials(conn)
                if 'credit_dossier.section3a_financial_forecast' in missing_tables:
                    seed_forecast(conn)
                simple_tables = set(SECTION3_TABLE_NAMES[2:])
                if missing_tables.intersection(simple_tables):
                    seed_simple_section3_tables(conn)
            contextualize_seeded_tables(conn, context, missing_tables)
            conn.commit()
    finally:
        if sys.path and sys.path[0] == intel_path:
            sys.path.pop(0)
        for name, module in saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def manufacture_client_data(client_name, industry, geography, progress_callback=None):
    def report(percent, stage):
        if progress_callback:
            progress_callback(percent, stage)

    report(5, 'Preparing client manufacturing context')
    client_slug = slugify(client_name)
    dbname = db_name_for_client(client_name)
    context = existing_or_new_context(client_slug, client_name, industry, geography)
    context.setdefault('client_name', client_name)
    context.setdefault('industry', industry)
    context.setdefault('geography', geography)

    configured_library_id, configured_documents = load_existing_mistral_assets(client_slug)
    library_id = configured_library_id
    documents = configured_documents
    missing_documents = missing_document_names(documents)
    report(15, 'Creating or validating client database')
    ensure_database(dbname)
    upload_error = None
    uploaded_document_names = []
    if missing_documents:
        report(30, 'Generating and uploading PDF source documents')
        try:
            # PDFs only exist locally for the upload operation and are removed immediately.
            with tempfile.TemporaryDirectory(prefix=f'{client_slug}_pdfs_') as temporary_directory:
                upload_paths = create_pdfs(temporary_directory, context, missing_documents)
                library_id, documents, uploaded_document_names = create_mistral_library_and_upload(
                    context,
                    upload_paths,
                    library_id=library_id,
                    existing_documents=documents,
                )
        except Exception as exc:
            upload_error = str(exc)
    report(65, 'Validating Mistral library sources')

    report(75, 'Generating PostgreSQL source tables')
    missing_tables = missing_client_tables(dbname)
    seed_tables(dbname, context, missing_tables)
    report(92, 'Registering client with the shared MCP')
    register_backend_mcp(client_name, dbname, library_id, documents)
    mcp_start = start_shared_mcp()
    report(100, 'Client data manufacturing completed')

    return {
        'clientName': client_name,
        'industry': industry,
        'geography': geography,
        'databaseName': dbname,
        'mcpFolder': str(SHARED_MCP_DIR),
        'mcpUrl': os.getenv('SHARED_MCP_URL', 'http://127.0.0.1:8010/mcp'),
        'mcpStarted': mcp_start['started'],
        'mcpReady': mcp_start['ready'],
        'mcpStatus': mcp_start['message'],
        'pdfCount': len(PDF_FILES),
        'generatedPdfCount': len(uploaded_document_names),
        'tableCount': 16,
        'seededTableCount': len(missing_tables),
        'mistralLibraryId': library_id,
        'uploadedPdfCount': len(uploaded_document_names),
        'availableMistralPdfCount': len(documents),
        'uploadError': upload_error,
    }


def drop_client_database(dbname):
    with psycopg.connect(**get_base_db_config('postgres'), autocommit=True) as conn:
        conn.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid();
            """,
            (dbname,),
        )
        conn.execute(psycopg.sql.SQL('DROP DATABASE IF EXISTS {};').format(psycopg.sql.Identifier(dbname)))


def delete_manufactured_client_data(client_name):
    """Remove all manufactured assets for one client after its final deal is deleted."""
    client_slug = slugify(client_name)
    dbname = db_name_for_client(client_name)
    # Preserve a generic template before a client folder such as intel_mcp is removed.
    ensure_mcp_template()
    library_id, _ = load_existing_mistral_assets(client_slug)
    client_mcp_dir = MCP_ROOT / f'{client_slug}_mcp'

    if library_id:
        # Existing clients retain their own runtime configuration even when the
        # reusable template intentionally excludes secrets.
        client_env = dotenv_values(client_mcp_dir / '.env') if client_mcp_dir.exists() else {}
        api_key = client_env.get('MISTRAL_API_KEY') or get_mistral_api_key()
        if not api_key:
            raise RuntimeError('MISTRAL_API_KEY is required to delete the client Mistral library.')
        try:
            Mistral(api_key=api_key).beta.libraries.delete(library_id=library_id)
        except Exception as exc:
            if '404' not in str(exc):
                raise

    drop_client_database(dbname)

    from database import get_connection

    with get_connection() as conn:
        conn.execute(
            'DELETE FROM mcp_client_registry WHERE client_match = %s;',
            (client_slug.replace('_', ' '),),
        )
        conn.commit()

    if client_mcp_dir.exists() and client_mcp_dir != MCP_TEMPLATE_DIR:
        shutil.rmtree(client_mcp_dir)

    return {'databaseName': dbname, 'mistralLibraryId': library_id}
