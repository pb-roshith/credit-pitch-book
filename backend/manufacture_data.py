import json
import os
import re
import shutil
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


ROOT_DIR = Path(__file__).resolve().parents[1]
MCP_ROOT = ROOT_DIR / 'mcp'
SOURCE_MCP_DIR = ROOT_DIR / 'intel_mcp'
GENERATED_ROOT = ROOT_DIR / 'generated_manufactured_data'

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


def slugify(value):
    slug = re.sub(r'[^a-z0-9]+', '_', value.lower()).strip('_')
    return slug or 'client'


def db_name_for_client(client_name):
    return f'{slugify(client_name)}_mcp_db'


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


def get_base_db_config(dbname='postgres'):
    env = dotenv_values(SOURCE_MCP_DIR / '.env')
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
    return os.getenv('MISTRAL_API_KEY') or dotenv_values(SOURCE_MCP_DIR / '.env').get('MISTRAL_API_KEY')


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


def create_pdfs(client_slug, context):
    docs_dir = GENERATED_ROOT / client_slug / 'pdfs'
    docs_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for filename in PDF_FILES:
        path = docs_dir / filename
        write_pdf(path, filename, context)
        paths.append(path)
    return paths


def create_mistral_library_and_upload(client_slug, context, pdf_paths):
    api_key = os.getenv('MISTRAL_API_KEY') or dotenv_values(SOURCE_MCP_DIR / '.env').get('MISTRAL_API_KEY')
    if not api_key:
        return None, []

    client = Mistral(api_key=api_key)
    library = client.beta.libraries.create(
        name=f'{context["client_name"]} MCP Library',
        description=f'Synthetic manufactured credit documents for {context["client_name"]}.',
    )
    documents = []
    for index, path in enumerate(pdf_paths, start=1):
        with path.open('rb') as handle:
            document = client.beta.libraries.documents.upload(
                library_id=library.id,
                file={'file_name': path.name, 'content': handle, 'content_type': 'application/pdf'},
            )
        documents.append(
            {
                'number': index,
                'document_id': document.id,
                'name': path.name,
                'tool_name': f'get_{path.stem.lower()}_content',
            }
        )
    return library.id, documents


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


def contextualize_seeded_tables(conn, context):
    current_year = datetime.now().year
    client_id = 1001
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
        SOURCE_MCP_DIR,
        target,
        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'),
    )

    source_env = dotenv_values(SOURCE_MCP_DIR / '.env')
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


def register_backend_mcp(client_name, port):
    from database import get_connection

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO mcp_client_registry (client_match, mcp_url, enabled)
            VALUES (%s, %s, TRUE)
            ON CONFLICT (client_match) DO UPDATE SET
                mcp_url = EXCLUDED.mcp_url,
                enabled = TRUE,
                updated_at = NOW();
            """,
            (slugify(client_name).replace('_', ' '), f'http://127.0.0.1:{port}/mcp'),
        )
        conn.commit()


def seed_tables(dbname, context):
    import sys

    intel_path = str(ROOT_DIR / 'intel_mcp')
    shadowed_modules = [
        'database',
        'table_config',
        'load_excel_tables',
        'load_section2_tables',
        'load_section3_tables',
    ]
    saved_modules = {name: sys.modules.get(name) for name in shadowed_modules}
    for name in shadowed_modules:
        sys.modules.pop(name, None)
    sys.path.insert(0, intel_path)
    try:
        from database import get_connection
        from load_excel_tables import create_table, insert_rows, read_excel
        from load_section2_tables import create_section2_tables, create_support_clients_table, seed_customer_information, seed_ownership_structure
        from load_section3_tables import create_section3_tables, seed_forecast, seed_historical_financials, seed_simple_section3_tables
        from table_config import TABLE_FILES

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
            for table_name, path in TABLE_FILES.items():
                columns, rows = read_excel(path)
                rows = generate_rows_for_table(table_name, columns, rows, context)
                create_table(conn, table_name, columns)
                insert_rows(conn, table_name, columns, rows)
            create_section2_tables(conn)
            seed_customer_information(conn)
            seed_ownership_structure(conn)
            create_section3_tables(conn)
            seed_historical_financials(conn)
            seed_forecast(conn)
            seed_simple_section3_tables(conn)
            contextualize_seeded_tables(conn, context)
            conn.commit()
    finally:
        if sys.path and sys.path[0] == intel_path:
            sys.path.pop(0)
        for name, module in saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def manufacture_client_data(client_name, industry, geography):
    client_slug = slugify(client_name)
    dbname = db_name_for_client(client_name)
    context = generate_context_with_agent(client_name, industry, geography)
    context['client_name'] = client_name
    context['industry'] = industry
    context['geography'] = geography

    ensure_database(dbname)
    pdf_paths = create_pdfs(client_slug, context)
    upload_error = None
    try:
        library_id, documents = create_mistral_library_and_upload(client_slug, context, pdf_paths)
    except Exception as exc:
        library_id, documents = None, []
        upload_error = str(exc)
    seed_tables(dbname, context)
    mcp_port = choose_mcp_port()
    mcp_folder = copy_client_mcp_folder(client_slug, dbname, library_id, documents, mcp_port)
    register_backend_mcp(client_name, mcp_port)

    return {
        'clientName': client_name,
        'industry': industry,
        'geography': geography,
        'databaseName': dbname,
        'mcpFolder': str(mcp_folder),
        'mcpUrl': f'http://127.0.0.1:{mcp_port}/mcp',
        'pdfFolder': str(GENERATED_ROOT / client_slug / 'pdfs'),
        'pdfCount': len(pdf_paths),
        'tableCount': 16,
        'mistralLibraryId': library_id,
        'uploadedPdfCount': len(documents),
        'uploadError': upload_error,
    }
