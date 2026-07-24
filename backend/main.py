from decimal import Decimal
import hashlib
import hmac
from html import escape
from io import BytesIO
import json
import os
import re
import secrets
import time
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from mistralai.client import Mistral
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from database import get_connection, init_db
from manufacture_data import manufacture_client_data
from mcp_client import call_mcp_tool, list_mcp_tools
from narrative_generation_agent import generate_narrative as run_narrative_generation_agent
from narrative_judge import judge_narrative as run_narrative_judge_agent
from source_discovery_agent import select_source_tools
from telemetry import configure_telemetry, get_tracer, trace_id_from_span


app = FastAPI(title='Credit Pitch Book API')

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv('FRONTEND_ORIGIN', 'http://localhost:5173')],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


class DealCreate(BaseModel):
    legalName: str = Field(min_length=1)
    industry: str = Field(min_length=1)
    geography: str = Field(min_length=1)
    customerType: str = Field(min_length=1)
    segment: str = Field(min_length=1)
    kycStatus: str = Field(min_length=1)
    facility: str = Field(min_length=1)
    amount: Decimal = Field(gt=0)
    pricing: str = Field(min_length=1)
    collateralRequired: str = Field(min_length=1)
    currency: str = Field(min_length=1)
    tenure: str = Field(min_length=1)
    repayment: str = Field(min_length=1)
    targetCompletionDate: str = Field(min_length=1)
    status: str = 'Draft'


class McpToolCall(BaseModel):
    arguments: dict = Field(default_factory=dict)


class NarrativeGenerateRequest(BaseModel):
    customInstructions: str = ''
    outputTemplate: str = ''
    username: str = ''


class NarrativeBulkGenerateRequest(NarrativeGenerateRequest):
    sectionNumbers: list[int] = Field(default_factory=list)


class NarrativeJudgeRequest(BaseModel):
    draftId: int | None = None


class NarrativeExportRequest(BaseModel):
    selectedDraftIds: dict[int, int] = Field(default_factory=dict)


class NarrativeEditRequest(BaseModel):
    content: str = Field(min_length=1)
    editedFromDraftId: int | None = None
    username: str = ''


class AuthRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class ManufactureDataRequest(BaseModel):
    clientName: str = Field(min_length=1)
    industry: str = Field(min_length=1)
    geography: str = Field(min_length=1)


def row_to_deal(row):
    return {
        'id': row['id'],
        'customer': row['legal_name'],
        'industry': row['industry'],
        'geography': row['geography'],
        'customerType': row['customer_type'],
        'segment': row['segment'],
        'kycStatus': row['kyc_status'],
        'facility': row['facility'],
        'currency': row['currency'],
        'amount': float(row['amount']),
        'tenure': row['tenure'],
        'pricing': row['pricing'],
        'repayment': row['repayment'],
        'collateral': 'Secured' if row['collateral_required'] == 'Yes' else 'Unsecured',
        'collateralRequired': row['collateral_required'],
        'due': row['target_completion_date'].isoformat(),
        'status': row['status'],
        'progress': row['progress'],
        'createdAt': row['created_at'].isoformat(),
        'updatedAt': row['updated_at'].isoformat(),
        'activity': [],
    }


def row_to_narrative_section(row):
    return {
        'number': str(row['section_number']).zfill(2),
        'sectionNumber': row['section_number'],
        'name': row['section_name'],
        'description': row['description'],
        'inputSources': row['input_sources'],
        'expectedOutput': row['expected_output'],
        'status': 'Pending',
    }


def row_to_narrative_draft(row):
    judge_metadata = row['judge_metadata'] or {}
    return {
        'draftId': row['draft_id'],
        'dealId': row['deal_id'],
        'sectionNumber': row['section_number'],
        'customer': row['customer_name'],
        'versionType': row['version_type'],
        'editedFromDraftId': row['edited_from_draft_id'],
        'editedBy': row['edited_by'],
        'customInstructions': row['custom_instructions'],
        'outputTemplate': row['output_template'],
        'discoveredSources': row['discovered_sources'] or [],
        'generationModel': row['generation_model'],
        'agentId': row['agent_id'],
        'conversationId': row['conversation_id'],
        'otelTraceId': row.get('otel_trace_id'),
        'sourceDiscoveryAgentId': row.get('source_discovery_agent_id'),
        'sourceDiscoveryConversationId': row.get('source_discovery_conversation_id'),
        'judge': {
            'judgeId': row['judge_id'],
            'confidenceScore': float(row['judge_confidence_score']) if row['judge_confidence_score'] is not None else None,
            'confidencePercent': round(float(row['judge_confidence_score']) * 100) if row['judge_confidence_score'] is not None else None,
            'explanation': row['judge_explanation'],
            'scoreExplanation': judge_metadata.get('scoreExplanation', ''),
            'remainingGapExplanation': judge_metadata.get('remainingGapExplanation', row['judge_explanation'] or ''),
            'metadata': judge_metadata,
        } if row.get('judge_id') or row.get('judge_confidence_score') is not None or row.get('judge_explanation') else None,
        'draft': row['generated_output'],
        'createdAt': row['created_at'].isoformat(),
    }


def row_to_export_version(row):
    return {
        'exportId': row['export_id'],
        'dealId': row['deal_id'],
        'filename': row['filename'],
        'selectedDraftIds': row['selected_draft_ids'] or {},
        'sectionCount': row['section_count'],
        'createdAt': row['created_at'].isoformat(),
    }


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 120000)
    return f'pbkdf2_sha256${salt}${digest.hex()}'


def verify_password(password, stored_hash):
    try:
        algorithm, salt, digest = stored_hash.split('$', 2)
    except ValueError:
        return False
    if algorithm != 'pbkdf2_sha256':
        return False
    candidate = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 120000).hex()
    return hmac.compare_digest(candidate, digest)


def strip_export_citations(text):
    cleaned = re.sub(r'\s*\[Source:[^\]]+\]', '', text or '')
    cleaned = re.sub(r'[ \t]+([.,;:])', r'\1', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def docx_paragraph(text='', bold=False):
    run_properties = '<w:rPr><w:b/></w:rPr>' if bold else ''
    if not text:
        return '<w:p/>'
    return (
        '<w:p><w:r>'
        f'{run_properties}'
        f'<w:t xml:space="preserve">{escape(text)}</w:t>'
        '</w:r></w:p>'
    )


def build_docx(title, section_rows):
    body_parts = [docx_paragraph(title, bold=True), docx_paragraph()]
    for section_title, content in section_rows:
        body_parts.append(docx_paragraph(section_title, bold=True))
        body_parts.append(docx_paragraph())
        for line in strip_export_citations(content).splitlines():
            body_parts.append(docx_paragraph(line.strip()))
        body_parts.append(docx_paragraph())

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>'
        f"{''.join(body_parts)}"
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>'
        '</w:body></w:document>'
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>'
    )

    buffer = BytesIO()
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as docx:
        docx.writestr('[Content_Types].xml', content_types_xml)
        docx.writestr('_rels/.rels', rels_xml)
        docx.writestr('word/document.xml', document_xml)
    return buffer.getvalue()


def compact_observability_payload(value, limit=5):
    if value is None:
        return {'count': 0, 'items': []}

    data = value.model_dump(mode='json') if hasattr(value, 'model_dump') else value
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        list_key = next(
            (
                key
                for key, item in data.items()
                if isinstance(item, list) and key not in {'errors'}
            ),
            None,
        )
        items = data.get(list_key, []) if list_key else []
    else:
        items = []

    return {
        'count': len(items),
        'items': items[:limit],
    }


def safe_observability_call(label, callback, limit=5):
    try:
        payload = compact_observability_payload(callback(), limit=limit)
        return {
            'label': label,
            'available': True,
            **payload,
        }
    except Exception as exc:
        return {
            'label': label,
            'available': False,
            'count': 0,
            'items': [],
            'error': str(exc),
        }


def get_mistral_observability_snapshot():
    api_key = os.getenv('MISTRAL_API_KEY')
    if not api_key:
        return {
            'enabled': False,
            'reason': 'MISTRAL_API_KEY is not configured.',
            'features': [],
        }

    client = Mistral(api_key=api_key)
    observability = client.beta.observability
    features = [
        safe_observability_call('Judges', lambda: observability.judges.list(page_size=10)),
        safe_observability_call('Traces', lambda: observability.traces.search(page_size=10)),
        safe_observability_call('Spans', lambda: observability.spans.search_spans(page_size=10)),
        safe_observability_call('Span Evaluations', lambda: observability.spans.search_span_evaluations(page_size=10)),
        safe_observability_call('Logs', lambda: observability.logs.search(page_size=10)),
        safe_observability_call('Datasets', lambda: observability.datasets.list(page_size=10)),
        safe_observability_call('Campaigns', lambda: observability.campaigns.list(page_size=10)),
        safe_observability_call('Chat Completion Events', lambda: observability.chat_completion_events.search(search_params={}, page_size=10)),
    ]
    return {
        'enabled': True,
        'features': features,
        'availableFeatureCount': len([feature for feature in features if feature['available']]),
        'errorFeatureCount': len([feature for feature in features if not feature['available']]),
    }


def observability_model_data(value):
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    return value if isinstance(value, dict) else {}


def observability_results(value):
    data = observability_model_data(value)
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    if isinstance(data.get('results'), list):
        return data['results']
    for nested_value in data.values():
        if isinstance(nested_value, dict) and isinstance(nested_value.get('results'), list):
            return nested_value['results']
    return []


def fetch_native_mistral_observability():
    api_key = os.getenv('MISTRAL_API_KEY')
    if not api_key:
        return {'enabled': False, 'tracesByConversation': {}, 'spansByTrace': {}, 'error': 'MISTRAL_API_KEY is not configured.'}

    client = Mistral(api_key=api_key)
    observability = client.beta.observability

    def fetch_feature(callback):
        try:
            return {'available': True, 'items': observability_results(callback()), 'error': None}
        except Exception as exc:
            return {'available': False, 'items': [], 'error': str(exc)}

    trace_feature = fetch_feature(lambda: observability.traces.search(page_size=100))
    span_feature = fetch_feature(lambda: observability.spans.search_spans(page_size=100))
    evaluation_feature = fetch_feature(lambda: observability.spans.search_latest_span_evaluations(page_size=100))
    log_feature = fetch_feature(lambda: observability.logs.search(page_size=100))
    traces = trace_feature['items']
    spans = span_feature['items']
    evaluations = evaluation_feature['items']
    logs = log_feature['items']

    traces_by_conversation = {
        trace['conversation_id']: trace
        for trace in traces
        if trace.get('conversation_id')
    }
    spans_by_trace = {}
    for span in spans:
        trace_id = span.get('trace_id')
        if trace_id:
            spans_by_trace.setdefault(trace_id, []).append(span)

    return {
        'enabled': any(feature['available'] for feature in (trace_feature, span_feature, evaluation_feature, log_feature)),
        'tracesByConversation': traces_by_conversation,
        'spansByTrace': spans_by_trace,
        'traceCount': len(traces),
        'spanCount': len(spans),
        'evaluationCount': len(evaluations),
        'logCount': len(logs),
        'features': {
            'traces': {'available': trace_feature['available'], 'error': trace_feature['error']},
            'spans': {'available': span_feature['available'], 'error': span_feature['error']},
            'evaluations': {'available': evaluation_feature['available'], 'error': evaluation_feature['error']},
            'logs': {'available': log_feature['available'], 'error': log_feature['error']},
        },
        'error': next((feature['error'] for feature in (trace_feature, span_feature, evaluation_feature, log_feature) if feature['error']), None),
    }


def native_metric(native_trace, field, fallback=None):
    if native_trace and native_trace.get(field) is not None:
        return native_trace[field]
    return fallback


def native_duration_ms(native_trace, fallback=None):
    duration_ns = native_metric(native_trace, 'duration_ns')
    return round(float(duration_ns) / 1_000_000) if duration_ns is not None else fallback


def normalize_native_spans(native_spans):
    return [
        {
            'name': span.get('span_name') or span.get('operation_name') or 'Mistral span',
            'durationMs': round(float(span['duration_ns']) / 1_000_000) if span.get('duration_ns') is not None else None,
            'status': 'failed' if str(span.get('status_code') or '').lower() == 'error' else 'success',
            'detail': span.get('tool_name') or span.get('request_model') or span.get('agent_name'),
            'spanId': span.get('span_id'),
        }
        for span in native_spans
    ]


def find_otel_span(spans, span_name):
    return next((span for span in spans if span['span_name'] == span_name), None)


def otel_attribute(span, name, fallback=None):
    if span and (span.get('attributes') or {}).get(name) is not None:
        return (span.get('attributes') or {})[name]
    return fallback


def normalize_otel_spans(spans):
    return [
        {
            'name': span['span_name'],
            'durationMs': span['duration_ms'],
            'status': span['status'],
            'detail': span.get('status_message') or span.get('workflow'),
            'spanId': span['span_id'],
        }
        for span in spans
    ]


def estimate_tokens(text):
    if not text:
        return 0
    return max(1, round(len(str(text)) / 4))


def record_observability_event(
    event_type,
    status,
    deal_id=None,
    section_number=None,
    draft_id=None,
    model=None,
    latency_ms=None,
    input_tokens=0,
    output_tokens=0,
    error_message=None,
    metadata=None,
):
    total_tokens = (input_tokens or 0) + (output_tokens or 0)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO ai_observability_events (
                event_type, deal_id, section_number, draft_id, model, status,
                latency_ms, input_tokens, output_tokens, total_tokens,
                estimated_cost, error_message, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb);
            """,
            (
                event_type,
                deal_id,
                section_number,
                draft_id,
                model,
                status,
                latency_ms,
                input_tokens,
                output_tokens,
                total_tokens,
                None,
                error_message,
                json.dumps(metadata or {}),
            ),
        )
        conn.commit()


def get_deal_row_or_404(deal_id):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute('SELECT * FROM deals WHERE id = %s;', (deal_id,))
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail='Deal not found')

    return row


def get_narrative_section_or_404(section_number):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute('SELECT * FROM narrative_sections WHERE section_number = %s;', (section_number,))
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail='Narrative section not found')

    return row


def moderate_custom_instructions(custom_instructions):
    if not custom_instructions.strip():
        return []

    api_key = os.getenv('MISTRAL_API_KEY')
    if not api_key:
        return []

    client = Mistral(api_key=api_key)
    response = client.classifiers.moderate(
        model=os.getenv('MISTRAL_MODERATION_MODEL', 'mistral-moderation-latest'),
        inputs=custom_instructions,
    )
    result = response.results[0] if response.results else None
    categories = result.categories if result else {}
    category_scores = result.category_scores if result else {}
    topics = sorted(set((categories or {}).keys()) | set((category_scores or {}).keys()))
    category_results = [
        {
            'topic': topic,
            'flagged': bool((categories or {}).get(topic, False)),
            'score': float((category_scores or {}).get(topic, 0) or 0),
        }
        for topic in topics
    ]
    flagged_categories = [name for name, flagged in (categories or {}).items() if flagged]
    if flagged_categories:
        raise HTTPException(
            status_code=400,
            detail={
                'code': 'moderation_failed',
                'message': 'Custom Instructions For AI did not pass moderation. Please revise the instructions before generating.',
                'categories': flagged_categories,
                'categoryResults': category_results,
            },
        )
    return category_results


def resolve_mcp_registry_for_client(client_name):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM mcp_client_registry
                WHERE enabled = TRUE AND POSITION(LOWER(client_match) IN LOWER(%s)) > 0
                ORDER BY LENGTH(client_match) DESC, registry_id ASC
                LIMIT 1;
                """,
                (client_name,),
            )
            return cur.fetchone()


def get_deal_mcp_context_or_403(deal_id):
    deal = get_deal_row_or_404(deal_id)
    registry = resolve_mcp_registry_for_client(deal['legal_name'])
    if not registry:
        raise HTTPException(
            status_code=403,
            detail='No MCP registry entry is enabled for this client.',
        )
    return deal, registry


def extract_tool_text(tool_result):
    content = tool_result.get('content') or []
    fragments = []
    for item in content:
        text = item.get('text') if isinstance(item, dict) else None
        if not text:
            continue
        try:
            parsed = json.loads(text)
            fragments.append(parsed.get('text') or text)
        except json.JSONDecodeError:
            fragments.append(text)
    return '\n\n'.join(fragments)


def extract_tool_payload(tool_result):
    structured_content = tool_result.get('structuredContent')
    if isinstance(structured_content, dict) and 'result' in structured_content:
        return structured_content['result']

    content = tool_result.get('content') or []
    text_values = []
    for item in content:
        text = item.get('text') if isinstance(item, dict) else None
        if not text:
            continue
        text_values.append(text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue
    if text_values:
        return text_values
    return None


def normalize_source_name(value):
    cleaned = re.sub(r'[^a-z0-9]+', ' ', value.lower())
    return re.sub(r'\s+', ' ', cleaned).strip()


def parse_input_sources(input_sources):
    return [
        source.strip()
        for source in input_sources.split(',')
        if source.strip()
    ]


SOURCE_ALIAS_RULES = [
    (
        ('crm', 'client website', 'company site', 'annual report', 'annual reports', 'external databases', 'capital iq', 'mca filings', 'customer business profile'),
        ('company profile', 'certificate of incorporation', 'moa aoa', 'pan card', 'gst registration', 'kyc identity proofs', 'kyc credit reports'),
    ),
    (
        ('financial summary', 'uploaded fs', 'financial statements', 'financial engine outputs', 'crdm'),
        ('income statement', 'balance sheet', 'cashflow statement', 'cash flow statement', 'projected financials', 'bank statements', 'net worth statement'),
    ),
    (
        ('core banking', 'rwa data', 'limits utilization', 'limits & utilization'),
        ('existing loan details', 'customer facilities', 'other financial institution exposure', 'customer financial information historical'),
    ),
    (
        ('los', 'loan requirements', 'facility structure'),
        ('purpose of loan', 'existing loan details', 'customer facilities', 'collateral guarantee information'),
    ),
    (
        ('collateral systems', 'collateral security'),
        ('asset details', 'property documents', 'collateral guarantee information'),
    ),
    (
        ('industry website', 'external market data', 'news feeds', 'industry analysis'),
        ('company profile', 'key customers suppliers', 'gst returns', 'income tax returns 3 years'),
    ),
    (
        ('internal rating', 'external ratings', 'movement in historical ratings'),
        ('kyc credit reports', 'customer financial information historical', 'income tax returns 3 years', 'gst returns'),
    ),
    (
        ('existing risk policies', 'credit policy templates', 'policy mapping'),
        ('purpose of loan', 'covenant description', 'credit committee resolution', 'documentation security exceptions', 'declarations'),
    ),
    (
        ('esg data providers', 'esg analysis'),
        ('company profile', 'declarations', 'gst registration', 'litigation details'),
    ),
    (
        ('declaration',),
        ('declarations',),
    ),
]

BROAD_SOURCE_TERMS = {'all modules above', 'all systems'}


def source_aliases(source_name):
    normalized_source = normalize_source_name(source_name)
    aliases = []
    for triggers, replacements in SOURCE_ALIAS_RULES:
        if any(normalize_source_name(trigger) in normalized_source for trigger in triggers):
            aliases.extend(replacements)
    return aliases


def source_candidates(source_name):
    return [source_name, *source_aliases(source_name)]


def is_broad_source(source_name):
    return normalize_source_name(source_name) in BROAD_SOURCE_TERMS


def readable_table_name(table_name):
    bare_name = table_name.split('.')[-1]
    bare_name = re.sub(r'^section\d+[a-z]?_', '', bare_name)
    bare_name = re.sub(r'^credit_', '', bare_name)
    return bare_name.replace('_', ' ')


def source_matches_table(source_name, table_name):
    normalized_source = normalize_source_name(source_name)
    normalized_table = normalize_source_name(readable_table_name(table_name))
    normalized_raw_table = normalize_source_name(table_name)
    if not normalized_source:
        return False
    return (
        normalized_source in normalized_table
        or normalized_table in normalized_source
        or normalized_source in normalized_raw_table
    )


def source_matches_tool(source_name, tool):
    if is_broad_source(source_name):
        return True
    normalized_source = normalize_source_name(source_name)
    normalized_tool = normalize_source_name(f"{tool['name']} {tool.get('description', '')}")
    return bool(normalized_source and normalized_source in normalized_tool)


async def discover_table_sources(registry, section, tools):
    tool_names = {tool['name'] for tool in tools}
    if 'list_credit_tables' not in tool_names or 'fetch_credit_table_rows' not in tool_names:
        return []

    table_result = await call_mcp_tool(registry['mcp_url'], 'list_credit_tables', {})
    table_names = extract_tool_payload(table_result)
    if not isinstance(table_names, list):
        return []

    input_sources = parse_input_sources(section['input_sources'])
    matched_tables = []
    for source_name in input_sources:
        for table_name in table_names:
            if not isinstance(table_name, str):
                continue
            if is_broad_source(source_name) or any(source_matches_table(candidate, table_name) for candidate in source_candidates(source_name)):
                matched_tables.append((source_name, table_name))

    unique_matches = []
    seen_tables = set()
    for source_name, table_name in matched_tables:
        if table_name in seen_tables:
            continue
        seen_tables.add(table_name)
        unique_matches.append((source_name, table_name))

    sources = []
    for source_name, table_name in unique_matches:
        try:
            result = await call_mcp_tool(
                registry['mcp_url'],
                'fetch_credit_table_rows',
                {'table_name': table_name, 'limit': 50},
            )
        except Exception:
            continue
        rows = extract_tool_payload(result)
        if not rows:
            continue
        text = json.dumps(rows, indent=2, default=str)
        sources.append(
            {
                'toolName': f'fetch_credit_table_rows:{table_name}',
                'description': f'Matched input source "{source_name}" to MCP table "{table_name}".',
                'score': 100,
                'text': text[:12000],
            }
        )

    return sources


def score_tool_for_section(tool, section):
    name = tool['name'].lower()
    description = (tool.get('description') or '').lower()
    section_text = ' '.join(
        [
            section['section_name'],
            section['description'],
            section['input_sources'],
            section['expected_output'],
        ]
    ).lower()

    score = 0
    for raw_word in section_text.replace('/', ' ').replace('&', ' ').replace(',', ' ').split():
        word = raw_word.strip('().:-_')
        if len(word) < 4:
            continue
        if word in name or word in description:
            score += 2

    section_two_hints = {
        'company': 8,
        'profile': 8,
        'moa': 6,
        'aoa': 6,
        'certificate': 5,
        'incorporation': 5,
        'kyc': 4,
        'identity': 4,
        'pan': 4,
        'customers': 3,
        'suppliers': 3,
        'credit_reports': 3,
        'litigation': 2,
    }
    if section['section_number'] == 2:
        for hint, weight in section_two_hints.items():
            if hint in name:
                score += weight

    if name.startswith('get_') and name.endswith('_content'):
        score += 1

    for source_name in parse_input_sources(section['input_sources']):
        if is_broad_source(source_name):
            score += 8
        if any(source_matches_tool(candidate, tool) for candidate in source_candidates(source_name)):
            score += 12

    return score


def extract_beta_conversation_text(response):
    fragments = []
    for output in getattr(response, 'outputs', []) or []:
        if getattr(output, 'type', None) != 'message.output':
            continue

        content = getattr(output, 'content', '')
        if isinstance(content, str):
            fragments.append(content)
            continue

        for chunk in content or []:
            text = getattr(chunk, 'text', None)
            if text:
                fragments.append(text)

    return '\n'.join(fragments).strip()


def parse_agent_tool_selection(agent_text, tools):
    valid_tool_names = {tool['name'] for tool in tools}
    candidate_payloads = []

    try:
        candidate_payloads.append(json.loads(agent_text))
    except json.JSONDecodeError:
        pass

    json_match = re.search(r'(\{.*\}|\[.*\])', agent_text, re.DOTALL)
    if json_match:
        try:
            candidate_payloads.append(json.loads(json_match.group(1)))
        except json.JSONDecodeError:
            pass

    for payload in candidate_payloads:
        if isinstance(payload, dict):
            selected = payload.get('toolNames') or payload.get('tools') or payload.get('selectedTools') or []
        else:
            selected = payload

        if not isinstance(selected, list):
            continue

        tool_names = [
            tool_name
            for tool_name in selected
            if isinstance(tool_name, str) and tool_name in valid_tool_names
        ]
        if tool_names:
            return tool_names

    return []


async def discover_sources(registry, section):
    tools = await list_mcp_tools(registry['mcp_url'])
    scored_tools = [
        {
            **tool,
            'score': score_tool_for_section(tool, section),
        }
        for tool in tools
    ]

    api_key = os.getenv('MISTRAL_API_KEY')
    agent_id = None
    conversation_id = None
    selected_tool_names = []
    input_tokens = 0
    output_tokens = 0
    token_usage_estimated = False
    if api_key:
        expanded_input_sources = [
            {
                'source': source,
                'aliases': source_aliases(source),
                'broadScope': is_broad_source(source),
            }
            for source in parse_input_sources(section['input_sources'])
        ]
        source_discovery_result = select_source_tools(
            api_key=api_key,
            model=os.getenv('MISTRAL_GENERATION_MODEL', 'mistral-large-latest'),
            section=section,
            expanded_input_sources=expanded_input_sources,
            tools=tools,
        )
        selected_tool_names = source_discovery_result['toolNames']
        agent_id = source_discovery_result['agentId']
        conversation_id = source_discovery_result['conversationId']
        input_tokens = source_discovery_result['inputTokens']
        output_tokens = source_discovery_result['outputTokens']
        token_usage_estimated = source_discovery_result['tokenUsageEstimated']

    if selected_tool_names:
        tool_by_name = {tool['name']: tool for tool in scored_tools}
        relevant_tools = [tool_by_name[name] for name in selected_tool_names if name in tool_by_name]
    else:
        relevant_tools = [tool for tool in scored_tools if tool['score'] > 0]
        relevant_tools.sort(key=lambda tool: tool['score'], reverse=True)

        relevant_tools = relevant_tools[:6]

    sources = await discover_table_sources(registry, section, tools)
    existing_source_keys = {source['toolName'] for source in sources}
    for tool in relevant_tools:
        if tool['name'] in {'list_credit_tables', 'describe_credit_table', 'fetch_credit_table_rows'}:
            continue
        if tool['name'] in existing_source_keys:
            continue
        try:
            result = await call_mcp_tool(registry['mcp_url'], tool['name'], {})
        except Exception:
            continue
        text = extract_tool_text(result)
        if text.strip():
            sources.append(
                {
                    'toolName': tool['name'],
                    'description': tool.get('description', ''),
                    'score': tool['score'],
                    'text': text[:6000],
                }
            )

    return {
        'availableTools': scored_tools,
        'selectedSources': sources,
        'agentId': agent_id,
        'conversationId': conversation_id,
        'inputTokens': input_tokens,
        'outputTokens': output_tokens,
        'tokenUsageEstimated': token_usage_estimated,
    }


def generate_narrative_text(deal, section, discovered_sources, custom_instructions, output_template):
    context = '\n\n'.join(
        f"SOURCE: {source['toolName']}\n{source['text']}"
        for source in discovered_sources
    )
    if not context.strip():
        raise HTTPException(status_code=422, detail='No relevant MCP source content was discovered.')

    api_key = os.getenv('MISTRAL_API_KEY')
    if not api_key:
        return {
            'draft': (
                f"# {section['section_name']}\n\n"
                f"Draft source material was discovered, but MISTRAL_API_KEY is not configured for AI generation.\n\n"
                f"{context[:4000]}"
            ),
            'agentId': None,
            'conversationId': None,
            'model': None,
        }

    client = Mistral(api_key=api_key)
    model = os.getenv('MISTRAL_GENERATION_MODEL', 'mistral-large-latest')
    agent = client.beta.agents.create(
        model=model,
        name='Credit Pitch Book Narrative Drafter',
        instructions=(
            'You write concise, evidence-grounded corporate credit narratives. '
            'Use only discovered source content. If a detail is not supported by sources, do not invent it. '
            'Add inline citations for material facts using the exact source label format [Source: source_name]. '
            'Use the SOURCE labels provided in discoveredSourceContent as source_name values. '
            'Every paragraph or bullet that uses source data must include at least one inline citation. '
            'Respect custom instructions and output template when provided. Return only the narrative content.'
        ),
        completion_args={
            'temperature': 0.2,
            'max_tokens': 2500,
        },
    )
    prompt = {
        'client': {
            'legalName': deal['legal_name'],
            'industry': deal['industry'],
            'geography': deal['geography'],
            'facility': deal['facility'],
        },
        'section': {
            'sectionNumber': section['section_number'],
            'sectionName': section['section_name'],
            'description': section['description'],
            'allowedInputSources': section['input_sources'],
            'expectedOutput': section['expected_output'],
        },
        'customInstructions': custom_instructions or 'None',
        'outputTemplate': output_template or 'No explicit template provided.',
        'citationInstruction': (
            'Cite generated content inline using exact source labels from discoveredSourceContent. '
            'Example: Intel has operated since 1968. [Source: section2_customer_information]'
        ),
        'discoveredSourceContent': context,
    }
    response = client.beta.conversations.start(
        agent_id=agent.id,
        inputs=json.dumps(prompt),
        store=False,
    )
    draft = extract_beta_conversation_text(response)
    if not draft:
        raise HTTPException(status_code=502, detail='Mistral beta agent returned an empty draft.')
    return {
        'draft': draft,
        'agentId': agent.id,
        'conversationId': response.conversation_id,
        'model': model,
    }


def judge_narrative_relevance(deal, section, discovered_sources, draft):
    api_key = os.getenv('MISTRAL_API_KEY')
    if not api_key:
        return None

    source_context = '\n\n'.join(
        f"SOURCE: {source['toolName']}\n{source['text']}"
        for source in discovered_sources
    )
    source_labels = [source['toolName'] for source in discovered_sources]
    if not source_context.strip() or not draft.strip():
        return None

    client = Mistral(api_key=api_key)
    model = os.getenv('MISTRAL_JUDGE_MODEL', os.getenv('MISTRAL_GENERATION_MODEL', 'mistral-large-latest'))
    try:
        judge = client.beta.observability.judges.create(
            name=f"Narrative Relevance Judge {deal['id']}-{section['section_number']}-{secrets.token_hex(4)}",
            description='Scores whether a credit narrative is grounded in its discovered MCP data sources.',
            model_name=model,
            output={
                'type': 'REGRESSION',
                'min': 0,
                'max': 1,
                'min_description': 'The narrative is unsupported by the source data or contains material hallucinations.',
                'max_description': 'The narrative is fully supported by the source data with no material hallucinations.',
            },
            instructions=(
                'You are a credit risk narrative relevance judge. Compare the generated narrative against the data sources. '
                'The conversation you judge contains a user message with the discovered data sources and the section requirements, '
                'followed by an assistant message containing the generated narrative. Judge the assistant message against the sources. '
                'Return a numeric score from 0 to 1. Score only source groundedness and relevance for this exact section. '
                'Do not use generic examples, reusable boilerplate, or facts that are not present in the supplied sources or generated narrative. '
                'Calibrate strictly: 1.00 is allowed only when every material claim is directly supported by supplied sources, '
                'all important source-derived claims are cited, and the expected output is fully addressed. '
                'Use 0.90-0.99 for strong drafts with small citation or coverage gaps. '
                'Use 0.75-0.89 for useful drafts with partial source coverage, weak support for some conclusions, or missing expected-output items. '
                'Use below 0.75 when unsupported claims, irrelevant content, or hallucination risk is material. '
                'If any material claim is not traceable to a source, do not score above 0.90. '
                'If the narrative only covers part of the expected output, do not score above 0.85. '
                'If citations are missing or too broad for several claims, do not score above 0.88. '
                'In the analysis, write bullet feedback only. Each bullet must mention a specific claim from the generated narrative and '
                'the exact source label that supports it, partially supports it, or fails to support it. '
                'Explain only the missing confidence gap implied by your score. If the score is high, give fewer and smaller gap bullets, '
                'but still explain why the score is not perfect unless it is exactly 1.00. '
                'If you assign exactly 1.00, the analysis must say "- No relevance, citation, or expected-output coverage gap found against the supplied sources." '
                'Do not invent revenue, EBITDA, market share, customer base, or operational metrics unless they appear in the supplied content.'
            ),
            tools=[],
        )
        result = client.beta.observability.judges.judge_conversation(
            judge_id=judge.id,
            messages=[
                {
                    'role': 'user',
                    'content': (
                        f"Client: {deal['legal_name']}\n"
                        f"Section: {section['section_number']} - {section['section_name']}\n"
                        f"Expected output: {section['expected_output']}\n"
                        f"Allowed input sources: {section['input_sources']}\n\n"
                        f"Available source labels: {', '.join(source_labels)}\n\n"
                        "Discovered data sources:\n"
                        f"{source_context[:30000]}\n\n"
                        "Judge only the next assistant message. Use the actual generated narrative and actual discovered sources above. "
                        "Return bullet points only. For every gap bullet, name the unsupported or weakly supported narrative claim and "
                        "the source label(s) involved. Do not repeat template examples from other companies or sections. "
                        "Apply strict score caps: unsupported material claim max 0.90; partial expected-output coverage max 0.85; "
                        "missing or broad citations across several claims max 0.88. Award 1.00 only when there is no relevance, citation, or coverage gap."
                    ),
                },
                {
                    'role': 'assistant',
                    'content': draft[:12000],
                }
            ],
            properties={
                'client': deal['legal_name'],
                'section_number': section['section_number'],
                'section_name': section['section_name'],
                'data_sources': source_context[:30000],
                'generated_narrative': draft[:12000],
            },
        )
        score = max(0, min(1, float(result.answer)))
        return {
            'judgeId': judge.id,
            'confidenceScore': score,
            'confidencePercent': round(score * 100),
            'explanation': result.analysis,
            'metadata': {
                'model': model,
                'answer': result.answer,
            },
        }
    except Exception as exc:
        return {
            'judgeId': None,
            'confidenceScore': None,
            'confidencePercent': None,
            'explanation': f'Judge evaluation could not be completed: {exc}',
            'metadata': {'error': str(exc), 'model': model},
        }


def store_narrative_draft(
    deal,
    registry,
    section,
    discovered_sources,
    custom_instructions,
    output_template,
    generation_result,
    source_discovery_agent_id=None,
    source_discovery_conversation_id=None,
    otel_trace_id=None,
    version_type='generated',
    edited_from_draft_id=None,
    edited_by=None,
):
    query = """
        INSERT INTO narrative_drafts (
            deal_id, section_number, customer_name, client_match, mcp_url,
            input_sources, expected_output, custom_instructions, output_template,
            discovered_sources, generated_output, generation_model, agent_id, conversation_id, otel_trace_id,
            source_discovery_agent_id, source_discovery_conversation_id,
            judge_id, judge_confidence_score, judge_explanation, judge_metadata,
            version_type, edited_from_draft_id, edited_by
        )
        VALUES (
            %(deal_id)s, %(section_number)s, %(customer_name)s, %(client_match)s, %(mcp_url)s,
            %(input_sources)s, %(expected_output)s, %(custom_instructions)s, %(output_template)s,
            %(discovered_sources)s::jsonb, %(generated_output)s, %(generation_model)s, %(agent_id)s, %(conversation_id)s, %(otel_trace_id)s,
            %(source_discovery_agent_id)s, %(source_discovery_conversation_id)s,
            %(judge_id)s, %(judge_confidence_score)s, %(judge_explanation)s, %(judge_metadata)s::jsonb,
            %(version_type)s, %(edited_from_draft_id)s, %(edited_by)s
        )
        RETURNING *;
    """
    source_metadata = [
        {
            'toolName': source['toolName'],
            'description': source['description'],
            'score': source['score'],
        }
        for source in discovered_sources
    ]
    payload = {
        'deal_id': deal['id'],
        'section_number': section['section_number'],
        'customer_name': deal['legal_name'],
        'client_match': registry['client_match'],
        'mcp_url': registry['mcp_url'],
        'input_sources': section['input_sources'],
        'expected_output': section['expected_output'],
        'custom_instructions': custom_instructions,
        'output_template': output_template,
        'discovered_sources': json.dumps(source_metadata),
        'generated_output': generation_result['draft'],
        'generation_model': generation_result.get('model'),
        'agent_id': generation_result.get('agentId'),
        'conversation_id': generation_result.get('conversationId'),
        'otel_trace_id': otel_trace_id,
        'source_discovery_agent_id': source_discovery_agent_id,
        'source_discovery_conversation_id': source_discovery_conversation_id,
        'judge_id': (generation_result.get('judge') or {}).get('judgeId'),
        'judge_confidence_score': (generation_result.get('judge') or {}).get('confidenceScore'),
        'judge_explanation': (generation_result.get('judge') or {}).get('explanation'),
        'judge_metadata': json.dumps((generation_result.get('judge') or {}).get('metadata') or {}),
        'version_type': version_type,
        'edited_from_draft_id': edited_from_draft_id,
        'edited_by': edited_by,
    }
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, payload)
            row = cur.fetchone()
            conn.commit()
            return row


@app.on_event('startup')
def startup():
    init_db()
    configure_telemetry()


@app.get('/api/health')
def health():
    return {'status': 'ok'}


@app.post('/api/auth/register', status_code=status.HTTP_201_CREATED)
def register_user(payload: AuthRequest):
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail='Username is required.')

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO app_users (username, password_hash)
                    VALUES (%s, %s)
                    RETURNING user_id, username, created_at;
                    """,
                    (username, hash_password(payload.password)),
                )
                row = cur.fetchone()
                conn.commit()
            except Exception as exc:
                conn.rollback()
                if 'unique' in str(exc).lower():
                    raise HTTPException(status_code=409, detail='Username already exists.') from exc
                raise

    return {
        'userId': row['user_id'],
        'username': row['username'],
        'createdAt': row['created_at'].isoformat(),
    }


@app.post('/api/auth/login')
def login_user(payload: AuthRequest):
    username = payload.username.strip()
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute('SELECT * FROM app_users WHERE username = %s;', (username,))
            row = cur.fetchone()

    if not row or not verify_password(payload.password, row['password_hash']):
        raise HTTPException(status_code=401, detail='Invalid username or password.')

    return {
        'userId': row['user_id'],
        'username': row['username'],
    }


@app.get('/api/deals')
def list_deals():
    query = """
        SELECT *
        FROM deals
        ORDER BY created_at DESC, id DESC;
    """
    with get_connection() as conn:
      with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query)
        return [row_to_deal(row) for row in cur.fetchall()]


@app.get('/api/narrative-sections')
def list_narrative_sections():
    query = """
        SELECT *
        FROM narrative_sections
        ORDER BY section_number ASC;
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query)
            return [row_to_narrative_section(row) for row in cur.fetchall()]


@app.post('/api/manufacture-data')
def manufacture_data(payload: ManufactureDataRequest):
    try:
        return manufacture_client_data(
            client_name=payload.clientName.strip(),
            industry=payload.industry.strip(),
            geography=payload.geography.strip(),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get('/api/observability')
def observability_dashboard(client_name: str | None = Query(default=None, alias='clientName')):
    selected_client = client_name.strip() if client_name and client_name.strip() else None
    selected_client_filter = selected_client or ''
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT legal_name AS name
                FROM deals
                UNION
                SELECT customer_name AS name
                FROM narrative_drafts
                ORDER BY name ASC;
                """
            )
            client_rows = cur.fetchall()

            cur.execute(
                """
                SELECT COUNT(*) AS count
                FROM deals
                WHERE (%s::text = '' OR legal_name = %s::text);
                """,
                (selected_client_filter, selected_client_filter),
            )
            deal_count = cur.fetchone()['count']

            cur.execute(
                """
                SELECT
                    COUNT(*) AS total_drafts,
                    COUNT(*) FILTER (WHERE version_type = 'generated') AS generated_drafts,
                    COUNT(*) FILTER (WHERE version_type = 'edited') AS edited_drafts,
                    COUNT(*) FILTER (WHERE judge_confidence_score IS NOT NULL) AS judged_drafts,
                    COUNT(*) FILTER (WHERE judge_confidence_score IS NULL) AS unjudged_drafts,
                    AVG(judge_confidence_score) AS average_judge_score
                FROM narrative_drafts
                WHERE (%s::text = '' OR customer_name = %s::text);
                """,
                (selected_client_filter, selected_client_filter),
            )
            draft_summary = cur.fetchone()

            cur.execute(
                """
                SELECT COUNT(*) AS count
                FROM narrative_export_versions nev
                LEFT JOIN deals d ON d.id = nev.deal_id
                WHERE (%s::text = '' OR d.legal_name = %s::text);
                """,
                (selected_client_filter, selected_client_filter),
            )
            export_count = cur.fetchone()['count']

            cur.execute(
                """
                SELECT
                    COUNT(*) AS total_requests,
                    COUNT(*) FILTER (WHERE aoe.status = 'success') AS successful_requests,
                    COUNT(*) FILTER (WHERE aoe.status <> 'success') AS failed_requests,
                    AVG(latency_ms) AS average_latency_ms,
                    SUM(input_tokens) AS input_tokens,
                    SUM(output_tokens) AS output_tokens,
                    SUM(total_tokens) AS total_tokens
                FROM ai_observability_events aoe
                LEFT JOIN deals d ON d.id = aoe.deal_id
                LEFT JOIN narrative_drafts nd ON nd.draft_id = aoe.draft_id
                WHERE (
                    %s::text = ''
                    OR d.legal_name = %s::text
                    OR nd.customer_name = %s::text
                );
                """,
                (selected_client_filter, selected_client_filter, selected_client_filter),
            )
            event_summary = cur.fetchone()

            cur.execute(
                """
                SELECT
                    COALESCE(model, 'unknown') AS name,
                    COUNT(*) AS count,
                    AVG(latency_ms) AS average_latency_ms,
                    SUM(input_tokens) AS input_tokens,
                    SUM(output_tokens) AS output_tokens,
                    SUM(total_tokens) AS total_tokens,
                    COUNT(*) FILTER (WHERE aoe.status <> 'success') AS failed_requests
                FROM ai_observability_events aoe
                LEFT JOIN deals d ON d.id = aoe.deal_id
                LEFT JOIN narrative_drafts nd ON nd.draft_id = aoe.draft_id
                WHERE (
                    %s::text = ''
                    OR d.legal_name = %s::text
                    OR nd.customer_name = %s::text
                )
                GROUP BY COALESCE(model, 'unknown')
                ORDER BY count DESC, name ASC
                LIMIT 8;
                """,
                (selected_client_filter, selected_client_filter, selected_client_filter),
            )
            performance_by_model_rows = cur.fetchall()

            cur.execute(
                """
                SELECT
                    event_type AS name,
                    COUNT(*) AS count,
                    AVG(latency_ms) AS average_latency_ms,
                    SUM(input_tokens) AS input_tokens,
                    SUM(output_tokens) AS output_tokens,
                    SUM(total_tokens) AS total_tokens,
                    COUNT(*) FILTER (WHERE aoe.status <> 'success') AS failed_requests
                FROM ai_observability_events aoe
                LEFT JOIN deals d ON d.id = aoe.deal_id
                LEFT JOIN narrative_drafts nd ON nd.draft_id = aoe.draft_id
                WHERE (
                    %s::text = ''
                    OR d.legal_name = %s::text
                    OR nd.customer_name = %s::text
                )
                GROUP BY event_type
                ORDER BY count DESC, name ASC;
                """,
                (selected_client_filter, selected_client_filter, selected_client_filter),
            )
            performance_by_use_case_rows = cur.fetchall()

            cur.execute(
                """
                SELECT
                    ns.section_number,
                    ns.section_name,
                    COUNT(nd.draft_id) AS draft_count,
                    COUNT(nd.draft_id) FILTER (WHERE nd.version_type = 'edited') AS edited_count,
                    COUNT(nd.draft_id) FILTER (WHERE nd.judge_confidence_score IS NOT NULL) AS judged_count,
                    AVG(nd.judge_confidence_score) AS average_judge_score,
                    MAX(nd.created_at) AS latest_draft_at
                FROM narrative_sections ns
                LEFT JOIN narrative_drafts nd
                    ON nd.section_number = ns.section_number
                    AND (%s::text = '' OR nd.customer_name = %s::text)
                GROUP BY ns.section_number, ns.section_name
                ORDER BY ns.section_number ASC;
                """,
                (selected_client_filter, selected_client_filter),
            )
            section_rows = cur.fetchall()

            cur.execute(
                """
                SELECT
                    nd.draft_id,
                    nd.deal_id,
                    nd.customer_name,
                    nd.section_number,
                    ns.section_name,
                    nd.version_type,
                    nd.input_sources,
                    nd.expected_output,
                    nd.custom_instructions,
                    nd.output_template,
                    nd.discovered_sources,
                    nd.generated_output,
                    nd.generation_model,
                    nd.agent_id,
                    nd.conversation_id,
                    nd.otel_trace_id,
                    nd.source_discovery_agent_id,
                    nd.source_discovery_conversation_id,
                    nd.judge_id,
                    nd.judge_confidence_score,
                    nd.judge_explanation,
                    nd.created_at
                FROM narrative_drafts
                nd
                JOIN narrative_sections ns ON ns.section_number = nd.section_number
                WHERE (%s::text = '' OR nd.customer_name = %s::text)
                ORDER BY created_at DESC, draft_id DESC
                LIMIT 50;
                """,
                (selected_client_filter, selected_client_filter),
            )
            recent_drafts = cur.fetchall()

            cur.execute(
                """
                SELECT nev.export_id, nev.deal_id, nev.filename, nev.section_count, nev.created_at
                FROM narrative_export_versions nev
                LEFT JOIN deals d ON d.id = nev.deal_id
                WHERE (%s::text = '' OR d.legal_name = %s::text)
                ORDER BY created_at DESC, export_id DESC
                LIMIT 8;
                """,
                (selected_client_filter, selected_client_filter),
            )
            recent_exports = cur.fetchall()

            cur.execute(
                """
                SELECT client_match, mcp_url, enabled, updated_at
                FROM mcp_client_registry
                ORDER BY client_match ASC;
                """
            )
            mcp_rows = cur.fetchall()

            cur.execute(
                """
                SELECT discovered_sources
                FROM narrative_drafts
                WHERE jsonb_array_length(discovered_sources) > 0
                    AND (%s::text = '' OR customer_name = %s::text);
                """,
                (selected_client_filter, selected_client_filter),
            )
            source_rows = cur.fetchall()

            cur.execute(
                """
                SELECT DISTINCT ON (aoe.draft_id)
                    aoe.draft_id, aoe.latency_ms, aoe.input_tokens, aoe.output_tokens, aoe.total_tokens
                FROM ai_observability_events aoe
                LEFT JOIN narrative_drafts nd ON nd.draft_id = aoe.draft_id
                WHERE aoe.event_type = 'narrative_generate'
                    AND aoe.draft_id IS NOT NULL
                    AND (%s::text = '' OR nd.customer_name = %s::text)
                ORDER BY aoe.draft_id, aoe.created_at DESC, aoe.event_id DESC;
                """,
                (selected_client_filter, selected_client_filter),
            )
            draft_event_rows = {row['draft_id']: row for row in cur.fetchall()}

            cur.execute(
                """
                SELECT DISTINCT ON (aoe.draft_id)
                    aoe.draft_id, aoe.latency_ms, aoe.input_tokens, aoe.output_tokens, aoe.total_tokens
                FROM ai_observability_events aoe
                LEFT JOIN narrative_drafts nd ON nd.draft_id = aoe.draft_id
                WHERE aoe.event_type = 'judge'
                    AND aoe.draft_id IS NOT NULL
                    AND (%s::text = '' OR nd.customer_name = %s::text)
                ORDER BY aoe.draft_id, aoe.created_at DESC, aoe.event_id DESC;
                """,
                (selected_client_filter, selected_client_filter),
            )
            judge_event_rows = {row['draft_id']: row for row in cur.fetchall()}

            cur.execute(
                """
                SELECT
                    os.trace_id, os.span_id, os.parent_span_id, os.span_name, os.status,
                    os.status_message, os.duration_ms, os.deal_id, os.section_number,
                    os.draft_id, os.workflow, os.attributes, os.start_time
                FROM otel_spans os
                LEFT JOIN deals d ON d.id = os.deal_id
                LEFT JOIN narrative_drafts nd
                    ON nd.otel_trace_id = os.trace_id OR nd.draft_id = os.draft_id
                WHERE (
                    %s::text = ''
                    OR d.legal_name = %s::text
                    OR nd.customer_name = %s::text
                )
                ORDER BY os.start_time ASC;
                """,
                (selected_client_filter, selected_client_filter, selected_client_filter),
            )
            otel_span_rows = cur.fetchall()

    # The dashboard is backed by locally exported OpenTelemetry spans. Existing
    # PostgreSQL events remain a fallback for drafts created before tracing.
    native_observability = {
        'tracesByConversation': {},
        'spansByTrace': {},
    }
    otel_spans_by_trace = {}
    otel_spans_by_draft = {}
    for otel_span in otel_span_rows:
        otel_spans_by_trace.setdefault(otel_span['trace_id'], []).append(otel_span)
        if otel_span['draft_id']:
            otel_spans_by_draft.setdefault(otel_span['draft_id'], []).append(otel_span)

    source_discovery_spans = [
        span for span in otel_span_rows
        if span['span_name'] == 'credit.source_discovery'
    ]
    source_discovery_summary = {
        'totalRequests': len(source_discovery_spans),
        'successfulRequests': sum(span['status'] != 'error' for span in source_discovery_spans),
        'failedRequests': sum(span['status'] == 'error' for span in source_discovery_spans),
        'averageLatencyMs': round(sum(span['duration_ms'] for span in source_discovery_spans) / len(source_discovery_spans))
        if source_discovery_spans else None,
        'inputTokens': sum(int(otel_attribute(span, 'gen_ai.usage.input_tokens', 0) or 0) for span in source_discovery_spans),
        'outputTokens': sum(int(otel_attribute(span, 'gen_ai.usage.output_tokens', 0) or 0) for span in source_discovery_spans),
        'retrievedSources': sum(int(otel_attribute(span, 'credit.source_count', 0) or 0) for span in source_discovery_spans),
        'estimatedTokenUsage': any(
            bool(otel_attribute(span, 'credit.token_usage_estimated', False))
            for span in source_discovery_spans
        ),
        'agentRuns': sum(1 for row in recent_drafts if row['source_discovery_agent_id']),
    }
    source_discovery_summary['totalTokens'] = (
        source_discovery_summary['inputTokens'] + source_discovery_summary['outputTokens']
    )

    event_workflows = {row['name']: row for row in performance_by_use_case_rows}

    def event_workflow_summary(event_type):
        row = event_workflows.get(event_type)
        if not row:
            return {
                'totalRequests': 0,
                'successfulRequests': 0,
                'failedRequests': 0,
                'averageLatencyMs': None,
                'inputTokens': 0,
                'outputTokens': 0,
                'totalTokens': 0,
            }
        total_requests = int(row['count'] or 0)
        failed_requests = int(row['failed_requests'] or 0)
        return {
            'totalRequests': total_requests,
            'successfulRequests': total_requests - failed_requests,
            'failedRequests': failed_requests,
            'averageLatencyMs': round(float(row['average_latency_ms'])) if row['average_latency_ms'] is not None else None,
            'inputTokens': int(row['input_tokens'] or 0),
            'outputTokens': int(row['output_tokens'] or 0),
            'totalTokens': int(row['total_tokens'] or 0),
        }

    narrative_generation_summary = event_workflow_summary('narrative_generate')
    judge_summary = event_workflow_summary('judge')
    workflow_summaries = [source_discovery_summary, narrative_generation_summary, judge_summary]
    overall_request_count = sum(summary['totalRequests'] for summary in workflow_summaries)
    overall_latency_total = sum(
        summary['averageLatencyMs'] * summary['totalRequests']
        for summary in workflow_summaries
        if summary['averageLatencyMs'] is not None
    )
    overall_latency_count = sum(
        summary['totalRequests']
        for summary in workflow_summaries
        if summary['averageLatencyMs'] is not None
    )
    overall_summary = {
        'totalRequests': overall_request_count,
        'successfulRequests': sum(summary['successfulRequests'] for summary in workflow_summaries),
        'failedRequests': sum(summary['failedRequests'] for summary in workflow_summaries),
        'averageLatencyMs': round(overall_latency_total / overall_latency_count) if overall_latency_count else None,
        'inputTokens': sum(summary['inputTokens'] for summary in workflow_summaries),
        'outputTokens': sum(summary['outputTokens'] for summary in workflow_summaries),
    }
    overall_summary['totalTokens'] = overall_summary['inputTokens'] + overall_summary['outputTokens']
    source_counts = {}
    for row in source_rows:
        for source in row['discovered_sources'] or []:
            tool_name = source.get('toolName')
            if tool_name:
                source_counts[tool_name] = source_counts.get(tool_name, 0) + 1

    section_metrics = [
        {
            'sectionNumber': row['section_number'],
            'sectionName': row['section_name'],
            'draftCount': row['draft_count'],
            'editedCount': row['edited_count'],
            'judgedCount': row['judged_count'],
            'averageJudgeScore': float(row['average_judge_score']) if row['average_judge_score'] is not None else None,
            'averageJudgePercent': round(float(row['average_judge_score']) * 100) if row['average_judge_score'] is not None else None,
            'latestDraftAt': row['latest_draft_at'].isoformat() if row['latest_draft_at'] else None,
        }
        for row in section_rows
    ]
    sections_with_drafts = len([section for section in section_metrics if section['draftCount'] > 0])
    total_sections = len(section_metrics)
    average_judge_score = (
        float(draft_summary['average_judge_score'])
        if draft_summary['average_judge_score'] is not None
        else None
    )
    observability_traces = []
    for row in recent_drafts:
        sources = row['discovered_sources'] or []
        citation_count = len(re.findall(r'\[Source:[^\]]+\]', row['generated_output'] or ''))
        source_count = len(sources)
        evaluation_score = round(float(row['judge_confidence_score']) * 100) if row['judge_confidence_score'] is not None else None
        event_row = draft_event_rows.get(row['draft_id'])
        judge_event_row = judge_event_rows.get(row['draft_id'])
        native_generation_trace = native_observability['tracesByConversation'].get(row['conversation_id'])
        native_discovery_trace = native_observability['tracesByConversation'].get(row['source_discovery_conversation_id'])
        native_trace_id = native_generation_trace.get('trace_id') if native_generation_trace else None
        native_spans = native_observability['spansByTrace'].get(native_trace_id, []) if native_trace_id else []
        otel_trace_id = row['otel_trace_id']
        otel_spans = list(otel_spans_by_trace.get(otel_trace_id, []))
        for judge_span in otel_spans_by_draft.get(row['draft_id'], []):
            if judge_span not in otel_spans:
                otel_spans.append(judge_span)
        otel_discovery_span = find_otel_span(otel_spans, 'credit.source_discovery')
        otel_generation_span = find_otel_span(otel_spans, 'credit.mistral.narrative_generation')
        otel_judge_span = find_otel_span(otel_spans, 'credit.mistral.judge')
        trace_id = otel_trace_id or native_trace_id or row['conversation_id'] or f"local-draft-{row['draft_id']}"
        workflow_metrics = {
            'sourceDiscovery': {
                'latencyMs': otel_discovery_span['duration_ms'] if otel_discovery_span else native_duration_ms(native_discovery_trace),
                'inputTokens': otel_attribute(otel_discovery_span, 'gen_ai.usage.input_tokens', native_metric(native_discovery_trace, 'input_tokens')),
                'outputTokens': otel_attribute(otel_discovery_span, 'gen_ai.usage.output_tokens', native_metric(native_discovery_trace, 'output_tokens')),
                'tokens': (
                    (otel_attribute(otel_discovery_span, 'gen_ai.usage.input_tokens', native_metric(native_discovery_trace, 'input_tokens')) or 0)
                    + (otel_attribute(otel_discovery_span, 'gen_ai.usage.output_tokens', native_metric(native_discovery_trace, 'output_tokens')) or 0)
                ) if otel_discovery_span or native_discovery_trace else None,
                'nativeTraceId': native_discovery_trace.get('trace_id') if native_discovery_trace else None,
                'tokenUsageEstimated': bool(otel_attribute(otel_discovery_span, 'credit.token_usage_estimated', False)),
            },
            'narrativeGenerate': {
                'latencyMs': otel_generation_span['duration_ms'] if otel_generation_span else native_duration_ms(native_generation_trace, event_row['latency_ms'] if event_row else None),
                'inputTokens': otel_attribute(otel_generation_span, 'gen_ai.usage.input_tokens', native_metric(native_generation_trace, 'input_tokens', event_row['input_tokens'] if event_row else None)),
                'outputTokens': otel_attribute(otel_generation_span, 'gen_ai.usage.output_tokens', native_metric(native_generation_trace, 'output_tokens', event_row['output_tokens'] if event_row else None)),
                'tokens': (
                    (otel_attribute(otel_generation_span, 'gen_ai.usage.input_tokens', native_metric(native_generation_trace, 'input_tokens')) or 0)
                    + (otel_attribute(otel_generation_span, 'gen_ai.usage.output_tokens', native_metric(native_generation_trace, 'output_tokens')) or 0)
                ) if otel_generation_span or native_generation_trace else (event_row['total_tokens'] if event_row else None),
                'nativeTraceId': native_trace_id,
            },
            'judge': {
                'latencyMs': otel_judge_span['duration_ms'] if otel_judge_span else (judge_event_row['latency_ms'] if judge_event_row else None),
                'inputTokens': otel_attribute(otel_judge_span, 'gen_ai.usage.input_tokens', judge_event_row['input_tokens'] if judge_event_row else None),
                'outputTokens': otel_attribute(otel_judge_span, 'gen_ai.usage.output_tokens', judge_event_row['output_tokens'] if judge_event_row else None),
                'tokens': (
                    (otel_attribute(otel_judge_span, 'gen_ai.usage.input_tokens') or 0)
                    + (otel_attribute(otel_judge_span, 'gen_ai.usage.output_tokens') or 0)
                ) if otel_judge_span else (judge_event_row['total_tokens'] if judge_event_row else None),
                'nativeTraceId': None,
            },
        }
        observability_traces.append(
            {
                'id': f"draft-{row['draft_id']}",
                'draftId': row['draft_id'],
                'userQuery': f"Generate Section {row['section_number']} narrative for {row['customer_name']}",
                'agentFlow': 'Source Discovery -> Retrieval -> Prompt Construction -> Mistral Agent Call -> Final Generation -> Save Draft',
                'mistralTraceId': trace_id,
                'traceId': trace_id,
                'latencyMs': workflow_metrics['narrativeGenerate']['latencyMs'],
                'model': row['generation_model'],
                'tokens': workflow_metrics['narrativeGenerate']['tokens'],
                'inputTokens': workflow_metrics['narrativeGenerate']['inputTokens'],
                'outputTokens': workflow_metrics['narrativeGenerate']['outputTokens'],
                'status': 'failed' if any(span['status'] == 'error' for span in otel_spans) or str((native_generation_trace or {}).get('status_code', '')).lower() == 'error' else 'success',
                'evaluationScore': evaluation_score,
                'feedback': row['judge_explanation'],
                'timestamp': row['created_at'].isoformat(),
                'sectionNumber': row['section_number'],
                'sectionName': row['section_name'],
                'customer': row['customer_name'],
                'spans': [
                    {'name': 'User Request', 'durationMs': None, 'status': 'success'},
                    {'name': 'Source Discovery', 'durationMs': None, 'status': 'success'},
                    {'name': 'Retrieval', 'durationMs': None, 'status': 'success', 'detail': f'{source_count} sources'},
                    {'name': 'Prompt Construction', 'durationMs': None, 'status': 'success'},
                    {'name': 'Mistral Agent Call', 'durationMs': None, 'status': 'success', 'detail': row['agent_id']},
                    {'name': 'Tool Call', 'durationMs': None, 'status': 'success'},
                    {'name': 'Final Generation', 'durationMs': None, 'status': 'success'},
                    {'name': 'Evaluation', 'durationMs': None, 'status': 'success' if evaluation_score is not None else 'not_run'},
                    {'name': 'Feedback', 'durationMs': None, 'status': 'available' if row['judge_explanation'] else 'not_available'},
                ],
                'nativeSpans': normalize_native_spans(native_spans),
                'otelSpans': normalize_otel_spans(otel_spans),
                'rag': {
                    'retrievedDocuments': [
                        {
                            'name': source.get('toolName'),
                            'sourceSystem': 'Postgres' if str(source.get('toolName', '')).startswith('fetch_credit_table_rows:') else 'Mistral PDF Library',
                            'chunkScore': source.get('score'),
                        }
                        for source in sources
                    ],
                    'citationCoveragePercent': round((citation_count / max(source_count, 1)) * 100) if source_count else 0,
                    'unsupportedClaimsCount': None,
                    'relevanceScore': evaluation_score,
                    'groundednessScore': evaluation_score,
                },
                'audit': {
                    'originalUserRequest': f"Generate Section {row['section_number']} narrative for {row['customer_name']}",
                    'retrievedSources': sources,
                    'finalPrompt': {
                        'section': row['section_name'],
                        'inputSources': row['input_sources'],
                        'expectedOutput': row['expected_output'],
                        'customInstructions': row['custom_instructions'] or '',
                        'outputTemplate': row['output_template'] or '',
                    },
                    'mistralResponse': row['generated_output'],
                    'citations': re.findall(r'\[Source:[^\]]+\]', row['generated_output'] or ''),
                    'evaluationScores': {
                        'judgeConfidencePercent': evaluation_score,
                    },
                    'metrics': workflow_metrics,
                    'sourceDiscovery': {
                        'agentId': row['source_discovery_agent_id'],
                        'conversationId': row['source_discovery_conversation_id'],
                        'selectedSourceCount': source_count,
                        'tokenUsageEstimated': workflow_metrics['sourceDiscovery']['tokenUsageEstimated'],
                    },
                    'openTelemetry': {
                        'available': bool(otel_spans),
                        'traceId': otel_trace_id,
                        'spanCount': len(otel_spans),
                    },
                    'nativeMistral': {
                        'available': bool(native_generation_trace),
                        'traceId': native_trace_id,
                        'conversationId': row['conversation_id'],
                        'sourceDiscoveryTraceId': workflow_metrics['sourceDiscovery']['nativeTraceId'],
                        'spanCount': len(native_spans),
                        'agentId': row['agent_id'],
                        'sourceDiscoveryAgentId': row['source_discovery_agent_id'],
                    },
                    'userFeedback': None,
                    'traceId': trace_id,
                    'timestamp': row['created_at'].isoformat(),
                },
            }
        )
    top_use_cases = [
        {'name': section['sectionName'], 'count': section['draftCount']}
        for section in sorted(section_metrics, key=lambda item: item['draftCount'], reverse=True)[:5]
        if section['draftCount'] > 0
    ]
    top_models = {}
    for row in recent_drafts:
        if row['generation_model']:
            top_models[row['generation_model']] = top_models.get(row['generation_model'], 0) + 1

    return {
        'summary': {
            'dealCount': deal_count,
            'totalSections': total_sections,
            'sectionsWithDrafts': sections_with_drafts,
            'sectionCoveragePercent': round((sections_with_drafts / total_sections) * 100) if total_sections else 0,
            'totalDrafts': draft_summary['total_drafts'],
            'generatedDrafts': draft_summary['generated_drafts'],
            'editedDrafts': draft_summary['edited_drafts'],
            'judgedDrafts': draft_summary['judged_drafts'],
            'unjudgedDrafts': draft_summary['unjudged_drafts'],
            'totalRequests': overall_summary['totalRequests'],
            'successfulRequests': overall_summary['successfulRequests'],
            'failedRequests': overall_summary['failedRequests'],
            'averageLatencyMs': overall_summary['averageLatencyMs'],
            'totalTokens': overall_summary['totalTokens'],
            'inputTokens': overall_summary['inputTokens'],
            'outputTokens': overall_summary['outputTokens'],
            'averageJudgeScore': average_judge_score,
            'averageJudgePercent': round(average_judge_score * 100) if average_judge_score is not None else None,
            'averageEvaluationScore': round(average_judge_score * 100) if average_judge_score is not None else None,
            'sourceDiscovery': source_discovery_summary,
            'narrativeGeneration': narrative_generation_summary,
            'judge': judge_summary,
            'exportCount': export_count,
            'mcpClientCount': len(mcp_rows),
            'topUseCases': top_use_cases,
            'topModels': [
                {'name': name, 'count': count}
                for name, count in sorted(top_models.items(), key=lambda item: item[1], reverse=True)[:5]
            ],
            'performanceByModel': [
                {
                    'name': row['name'],
                    'count': row['count'],
                    'averageLatencyMs': round(float(row['average_latency_ms'])) if row['average_latency_ms'] is not None else None,
                    'inputTokens': int(row['input_tokens']) if row['input_tokens'] is not None else 0,
                    'outputTokens': int(row['output_tokens']) if row['output_tokens'] is not None else 0,
                    'totalTokens': int(row['total_tokens']) if row['total_tokens'] is not None else 0,
                    'failedRequests': row['failed_requests'],
                }
                for row in performance_by_model_rows
            ],
            'performanceByUseCase': [
                {
                    'name': 'Source Discovery',
                    'count': source_discovery_summary['totalRequests'],
                    'averageLatencyMs': source_discovery_summary['averageLatencyMs'],
                    'inputTokens': source_discovery_summary['inputTokens'],
                    'outputTokens': source_discovery_summary['outputTokens'],
                    'totalTokens': source_discovery_summary['totalTokens'],
                    'failedRequests': source_discovery_summary['failedRequests'],
                }
            ] + [
                {
                    'name': row['name'],
                    'count': row['count'],
                    'averageLatencyMs': round(float(row['average_latency_ms'])) if row['average_latency_ms'] is not None else None,
                    'inputTokens': int(row['input_tokens']) if row['input_tokens'] is not None else 0,
                    'outputTokens': int(row['output_tokens']) if row['output_tokens'] is not None else 0,
                    'totalTokens': int(row['total_tokens']) if row['total_tokens'] is not None else 0,
                    'failedRequests': row['failed_requests'],
                }
                for row in performance_by_use_case_rows
            ],
        },
        'traces': observability_traces,
        'clients': [row['name'] for row in client_rows if row['name']],
        'selectedClient': selected_client,
        'sections': section_metrics,
        'topSources': [
            {'toolName': tool_name, 'count': count}
            for tool_name, count in sorted(source_counts.items(), key=lambda item: item[1], reverse=True)[:12]
        ],
        'recentDrafts': [
            {
                'draftId': row['draft_id'],
                'dealId': row['deal_id'],
                'customer': row['customer_name'],
                'sectionNumber': row['section_number'],
                'versionType': row['version_type'],
                'judgeConfidencePercent': round(float(row['judge_confidence_score']) * 100) if row['judge_confidence_score'] is not None else None,
                'createdAt': row['created_at'].isoformat(),
            }
            for row in recent_drafts
        ],
        'recentExports': [
            {
                'exportId': row['export_id'],
                'dealId': row['deal_id'],
                'filename': row['filename'],
                'sectionCount': row['section_count'],
                'createdAt': row['created_at'].isoformat(),
            }
            for row in recent_exports
        ],
        'mcpClients': [
            {
                'clientMatch': row['client_match'],
                'mcpUrl': row['mcp_url'],
                'enabled': row['enabled'],
                'updatedAt': row['updated_at'].isoformat(),
            }
            for row in mcp_rows
        ],
        'mistralObservability': get_mistral_observability_snapshot(),
        'openTelemetry': {
            'enabled': True,
            'spanCount': len(otel_span_rows),
        },
    }


@app.post('/api/deals', status_code=status.HTTP_201_CREATED)
def create_deal(deal: DealCreate):
    progress = 15 if deal.status == 'Draft' else 30
    query = """
        INSERT INTO deals (
            legal_name, industry, geography, customer_type, segment, kyc_status,
            facility, amount, pricing, collateral_required, currency, tenure,
            repayment, target_completion_date, status, progress
        )
        VALUES (
            %(legal_name)s, %(industry)s, %(geography)s, %(customer_type)s, %(segment)s, %(kyc_status)s,
            %(facility)s, %(amount)s, %(pricing)s, %(collateral_required)s, %(currency)s, %(tenure)s,
            %(repayment)s, %(target_completion_date)s, %(status)s, %(progress)s
        )
        RETURNING *;
    """
    payload = {
        'legal_name': deal.legalName,
        'industry': deal.industry,
        'geography': deal.geography,
        'customer_type': deal.customerType,
        'segment': deal.segment,
        'kyc_status': deal.kycStatus,
        'facility': deal.facility,
        'amount': deal.amount,
        'pricing': deal.pricing,
        'collateral_required': deal.collateralRequired,
        'currency': deal.currency,
        'tenure': deal.tenure,
        'repayment': deal.repayment,
        'target_completion_date': deal.targetCompletionDate,
        'status': deal.status,
        'progress': progress,
    }

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, payload)
            row = cur.fetchone()
            conn.commit()
            return row_to_deal(row)


@app.get('/api/deals/{deal_id}')
def get_deal(deal_id: int):
    row = get_deal_row_or_404(deal_id)
    return row_to_deal(row)


@app.get('/api/deals/{deal_id}/mcp')
def get_deal_mcp_availability(deal_id: int):
    row = get_deal_row_or_404(deal_id)
    registry = resolve_mcp_registry_for_client(row['legal_name'])
    return {
        'dealId': deal_id,
        'customer': row['legal_name'],
        'enabled': bool(registry),
        'clientMatch': registry['client_match'] if registry else None,
        'mcpUrl': registry['mcp_url'] if registry else None,
        'reason': 'Matching MCP registry entry found.' if registry else 'No MCP registry entry is enabled for this client.',
    }


@app.get('/api/deals/{deal_id}/mcp/tools')
async def get_deal_mcp_tools(deal_id: int):
    row, registry = get_deal_mcp_context_or_403(deal_id)
    tools = await list_mcp_tools(registry['mcp_url'])
    return {
        'dealId': deal_id,
        'customer': row['legal_name'],
        'clientMatch': registry['client_match'],
        'mcpUrl': registry['mcp_url'],
        'tools': tools,
    }


@app.post('/api/deals/{deal_id}/mcp/tools/{tool_name}')
async def run_deal_mcp_tool(deal_id: int, tool_name: str, payload: McpToolCall):
    row, registry = get_deal_mcp_context_or_403(deal_id)
    result = await call_mcp_tool(registry['mcp_url'], tool_name, payload.arguments)
    return {
        'dealId': deal_id,
        'customer': row['legal_name'],
        'clientMatch': registry['client_match'],
        'toolName': tool_name,
        'result': result,
    }


@app.post('/api/deals/{deal_id}/narratives/{section_number}/generate')
async def generate_narrative(deal_id: int, section_number: int, payload: NarrativeGenerateRequest):
    moderate_custom_instructions(payload.customInstructions)
    deal, registry = get_deal_mcp_context_or_403(deal_id)
    section = get_narrative_section_or_404(section_number)
    return await generate_narrative_for_section(deal_id, deal, registry, section, payload)


async def generate_narrative_for_section(deal_id, deal, registry, section, payload):
    started_at = time.perf_counter()
    draft_row = None
    generation_result = {}
    tracer = get_tracer()
    with tracer.start_as_current_span(
        'credit.narrative.generate',
        attributes={
            'credit.workflow': 'narrative_generation',
            'credit.deal_id': deal_id,
            'credit.section_number': section['section_number'],
            'credit.client': deal['legal_name'],
        },
    ) as root_span:
        otel_trace_id = trace_id_from_span(root_span)
        try:
            with tracer.start_as_current_span('credit.source_discovery') as span:
                discovery = await discover_sources(registry, section)
                span.set_attribute('credit.source_count', len(discovery['selectedSources']))
                span.set_attribute('credit.mcp_url', registry['mcp_url'])
                span.set_attribute('gen_ai.usage.input_tokens', discovery['inputTokens'])
                span.set_attribute('gen_ai.usage.output_tokens', discovery['outputTokens'])
                span.set_attribute('credit.token_usage_estimated', discovery['tokenUsageEstimated'])
                span.set_attribute('credit.agent_id', discovery['agentId'] or '')
                span.set_attribute('credit.conversation_id', discovery['conversationId'] or '')

            with tracer.start_as_current_span('credit.prompt_construction') as span:
                source_text = '\n\n'.join(source.get('text', '') for source in discovery['selectedSources'])
                input_tokens = estimate_tokens(source_text) + estimate_tokens(payload.customInstructions) + estimate_tokens(payload.outputTemplate)
                span.set_attribute('credit.source_count', len(discovery['selectedSources']))
                span.set_attribute('gen_ai.usage.input_tokens', input_tokens)
                span.set_attribute('credit.custom_instructions', bool(payload.customInstructions.strip()))
                span.set_attribute('credit.output_template', bool(payload.outputTemplate.strip()))

            with tracer.start_as_current_span('credit.mistral.narrative_generation') as span:
                generation_result = run_narrative_generation_agent(
                    api_key=os.getenv('MISTRAL_API_KEY'),
                    model=os.getenv('MISTRAL_GENERATION_MODEL', 'mistral-large-latest'),
                    deal=deal,
                    section=section,
                    discovered_sources=discovery['selectedSources'],
                    custom_instructions=payload.customInstructions,
                    output_template=payload.outputTemplate,
                )
                output_tokens = estimate_tokens(generation_result.get('draft', ''))
                span.set_attribute('gen_ai.request.model', generation_result.get('model') or 'unknown')
                span.set_attribute('gen_ai.usage.input_tokens', input_tokens)
                span.set_attribute('gen_ai.usage.output_tokens', output_tokens)
                span.set_attribute('credit.mistral_conversation_id', generation_result.get('conversationId') or '')

            with tracer.start_as_current_span('credit.postgres.save_draft'):
                draft_row = store_narrative_draft(
                    deal=deal,
                    registry=registry,
                    section=section,
                    discovered_sources=discovery['selectedSources'],
                    custom_instructions=payload.customInstructions,
                    output_template=payload.outputTemplate,
                    generation_result=generation_result,
                    source_discovery_agent_id=discovery.get('agentId'),
                    source_discovery_conversation_id=discovery.get('conversationId'),
                    otel_trace_id=otel_trace_id,
                    edited_by=payload.username or None,
                )

            root_span.set_attribute('credit.draft_id', draft_row['draft_id'])
            root_span.set_attribute('credit.source_count', len(discovery['selectedSources']))
            record_observability_event(
                event_type='narrative_generate',
                status='success',
                deal_id=deal_id,
                section_number=section['section_number'],
                draft_id=draft_row['draft_id'],
                model=generation_result.get('model'),
                latency_ms=round((time.perf_counter() - started_at) * 1000),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                metadata={'sourceCount': len(discovery['selectedSources']), 'otelTraceId': otel_trace_id},
            )
        except Exception as exc:
            record_observability_event(
                event_type='narrative_generate',
                status='failed',
                deal_id=deal_id,
                section_number=section['section_number'],
                model=generation_result.get('model'),
                latency_ms=round((time.perf_counter() - started_at) * 1000),
                error_message=str(exc),
                metadata={'otelTraceId': otel_trace_id},
            )
            raise
    return {
        'dealId': deal_id,
        'customer': deal['legal_name'],
        'draftId': draft_row['draft_id'],
        'savedAt': draft_row['created_at'].isoformat(),
        'section': row_to_narrative_section(section),
        'clientMatch': registry['client_match'],
        'mcpUrl': registry['mcp_url'],
        'inputSources': section['input_sources'],
        'expectedOutput': section['expected_output'],
        'discoveredSources': [
            {
                'toolName': source['toolName'],
                'description': source['description'],
                'score': source['score'],
            }
            for source in discovery['selectedSources']
        ],
        'sourceDiscoveryAgentId': discovery.get('agentId'),
        'sourceDiscoveryConversationId': discovery.get('conversationId'),
        'generationAgentId': generation_result.get('agentId'),
        'generationConversationId': generation_result.get('conversationId'),
        'generationModel': generation_result.get('model'),
        'judge': None,
        'draft': generation_result['draft'],
    }


@app.post('/api/deals/{deal_id}/narratives/generate-all')
async def generate_all_narratives(deal_id: int, payload: NarrativeBulkGenerateRequest):
    moderate_custom_instructions(payload.customInstructions)
    deal, registry = get_deal_mcp_context_or_403(deal_id)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if payload.sectionNumbers:
                cur.execute(
                    """
                    SELECT *
                    FROM narrative_sections
                    WHERE section_number = ANY(%s)
                    ORDER BY section_number ASC;
                    """,
                    (payload.sectionNumbers,),
                )
            else:
                cur.execute(
                    """
                    SELECT *
                    FROM narrative_sections
                    ORDER BY section_number ASC;
                    """
                )
            sections = cur.fetchall()

    requested_numbers = set(payload.sectionNumbers)
    found_numbers = {section['section_number'] for section in sections}
    results = []
    for missing_number in sorted(requested_numbers - found_numbers):
        results.append(
            {
                'sectionNumber': missing_number,
                'status': 'error',
                'message': 'Narrative section not found.',
            }
        )

    for section in sections:
        try:
            result = await generate_narrative_for_section(deal_id, deal, registry, section, payload)
            results.append(
                {
                    'sectionNumber': section['section_number'],
                    'sectionName': section['section_name'],
                    'status': 'drafted',
                    'draftId': result['draftId'],
                    'savedAt': result['savedAt'],
                    'judge': result.get('judge'),
                }
            )
        except HTTPException as exc:
            detail = exc.detail
            results.append(
                {
                    'sectionNumber': section['section_number'],
                    'sectionName': section['section_name'],
                    'status': 'error',
                    'message': detail.get('message') if isinstance(detail, dict) else str(detail),
                }
            )
        except Exception as exc:
            results.append(
                {
                    'sectionNumber': section['section_number'],
                    'sectionName': section['section_name'],
                    'status': 'error',
                    'message': str(exc),
                }
            )

    drafted_count = len([result for result in results if result['status'] == 'drafted'])
    return {
        'dealId': deal_id,
        'customer': deal['legal_name'],
        'requestedCount': len(payload.sectionNumbers) if payload.sectionNumbers else len(sections),
        'draftedCount': drafted_count,
        'errorCount': len(results) - drafted_count,
        'results': sorted(results, key=lambda result: result['sectionNumber']),
    }


@app.post('/api/deals/{deal_id}/narratives/{section_number}/judge')
async def run_narrative_judge(deal_id: int, section_number: int, payload: NarrativeJudgeRequest):
    started_at = time.perf_counter()
    deal, registry = get_deal_mcp_context_or_403(deal_id)
    section = get_narrative_section_or_404(section_number)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if payload.draftId:
                cur.execute(
                    """
                    SELECT *
                    FROM narrative_drafts
                    WHERE draft_id = %s AND deal_id = %s AND section_number = %s;
                    """,
                    (payload.draftId, deal_id, section_number),
                )
            else:
                cur.execute(
                    """
                    SELECT *
                    FROM narrative_drafts
                    WHERE deal_id = %s AND section_number = %s
                    ORDER BY created_at DESC, draft_id DESC
                    LIMIT 1;
                    """,
                    (deal_id, section_number),
                )
            draft_row = cur.fetchone()

    if not draft_row:
        raise HTTPException(status_code=404, detail='No generated draft found for this section.')

    discovered_sources = []
    for source in draft_row['discovered_sources'] or []:
        tool_name = source.get('toolName', '')
        if not tool_name:
            continue
        try:
            if tool_name.startswith('fetch_credit_table_rows:'):
                table_name = tool_name.split(':', 1)[1]
                result = await call_mcp_tool(
                    registry['mcp_url'],
                    'fetch_credit_table_rows',
                    {'table_name': table_name, 'limit': 50},
                )
                payload = extract_tool_payload(result)
                text = json.dumps(payload, indent=2, default=str) if payload else ''
            else:
                result = await call_mcp_tool(registry['mcp_url'], tool_name, {})
                text = extract_tool_text(result)
        except Exception:
            text = ''

        if text.strip():
            discovered_sources.append(
                {
                    'toolName': tool_name,
                    'description': source.get('description', ''),
                    'score': source.get('score', 0),
                    'text': text[:12000],
                }
            )

    if not discovered_sources:
        raise HTTPException(status_code=422, detail='No source content is available to judge this draft.')

    source_text = '\n\n'.join(source.get('text', '') for source in discovered_sources)
    judge_input_tokens = estimate_tokens(source_text) + estimate_tokens(draft_row['generated_output'])
    tracer = get_tracer()
    try:
        with tracer.start_as_current_span(
            'credit.mistral.judge',
            attributes={
                'credit.workflow': 'narrative_judge',
                'credit.deal_id': deal_id,
                'credit.section_number': section_number,
                'credit.draft_id': draft_row['draft_id'],
                'credit.client': deal['legal_name'],
                'gen_ai.usage.input_tokens': judge_input_tokens,
            },
        ) as span:
            judge_result = run_narrative_judge_agent(
                api_key=os.getenv('MISTRAL_API_KEY'),
                model=os.getenv('MISTRAL_JUDGE_MODEL', os.getenv('MISTRAL_GENERATION_MODEL', 'mistral-large-latest')),
                deal=deal,
                section=section,
                discovered_sources=discovered_sources,
                draft=draft_row['generated_output'],
            )
            span.set_attribute('gen_ai.usage.output_tokens', estimate_tokens((judge_result or {}).get('explanation', '')))
            span.set_attribute('credit.judge_id', (judge_result or {}).get('judgeId') or '')
    except Exception as exc:
        record_observability_event(
            event_type='judge',
            status='failed',
            deal_id=deal_id,
            section_number=section_number,
            draft_id=draft_row['draft_id'],
            model=os.getenv('MISTRAL_JUDGE_MODEL', os.getenv('MISTRAL_GENERATION_MODEL', 'mistral-large-latest')),
            latency_ms=round((time.perf_counter() - started_at) * 1000),
            error_message=str(exc),
        )
        raise

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE narrative_drafts
                SET judge_id = %s,
                    judge_confidence_score = %s,
                    judge_explanation = %s,
                    judge_metadata = %s::jsonb
                WHERE draft_id = %s
                RETURNING *;
                """,
                (
                    (judge_result or {}).get('judgeId'),
                    (judge_result or {}).get('confidenceScore'),
                    (judge_result or {}).get('explanation'),
                    json.dumps((judge_result or {}).get('metadata') or {}),
                    draft_row['draft_id'],
                ),
            )
            updated_row = cur.fetchone()
            conn.commit()

    record_observability_event(
        event_type='judge',
        status='success' if (judge_result or {}).get('confidenceScore') is not None else 'failed',
        deal_id=deal_id,
        section_number=section_number,
        draft_id=draft_row['draft_id'],
        model=(judge_result or {}).get('metadata', {}).get('model'),
        latency_ms=round((time.perf_counter() - started_at) * 1000),
        input_tokens=judge_input_tokens,
        output_tokens=estimate_tokens((judge_result or {}).get('explanation', '')),
        error_message=(judge_result or {}).get('metadata', {}).get('error'),
        metadata={'confidenceScore': (judge_result or {}).get('confidenceScore')},
    )
    return row_to_narrative_draft(updated_row)


@app.post('/api/deals/{deal_id}/narratives/export')
def export_narrative_drafts(deal_id: int, payload: NarrativeExportRequest):
    started_at = time.perf_counter()
    deal = get_deal_row_or_404(deal_id)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM narrative_sections
                ORDER BY section_number ASC;
                """
            )
            sections = cur.fetchall()

            selected_rows = {}
            if payload.selectedDraftIds:
                selected_ids = list(payload.selectedDraftIds.values())
                cur.execute(
                    """
                    SELECT *
                    FROM narrative_drafts
                    WHERE deal_id = %s AND draft_id = ANY(%s);
                    """,
                    (deal_id, selected_ids),
                )
                for row in cur.fetchall():
                    selected_rows[row['section_number']] = row

            cur.execute(
                """
                SELECT DISTINCT ON (section_number) *
                FROM narrative_drafts
                WHERE deal_id = %s
                ORDER BY section_number ASC, created_at DESC, draft_id DESC;
                """,
                (deal_id,),
            )
            latest_rows = {row['section_number']: row for row in cur.fetchall()}

    section_rows = []
    exported_count = 0

    for section in sections:
        section_number = section['section_number']
        draft_row = selected_rows.get(section_number) or latest_rows.get(section_number)
        if not draft_row:
            continue

        exported_count += 1
        section_rows.append(
            (
                f"{str(section_number).zfill(2)} {section['section_name']}",
                draft_row['generated_output'],
            )
        )

    if exported_count == 0:
        raise HTTPException(status_code=404, detail='No narrative drafts are available to export.')

    safe_customer = re.sub(r'[^A-Za-z0-9_-]+', '_', deal['legal_name']).strip('_') or 'credit_pitch_book'
    filename = f"{safe_customer}_narrative_draft.docx"
    docx_content = build_docx(f"Credit Pitch Book Draft - {deal['legal_name']}", section_rows)
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO narrative_export_versions (
                    deal_id, filename, selected_draft_ids, section_count, file_content
                )
                VALUES (%s, %s, %s::jsonb, %s, %s)
                RETURNING *;
                """,
                (
                    deal_id,
                    filename,
                    json.dumps(payload.selectedDraftIds),
                    exported_count,
                    docx_content,
                ),
            )
            cur.fetchone()
            conn.commit()

    record_observability_event(
        event_type='export',
        status='success',
        deal_id=deal_id,
        latency_ms=round((time.perf_counter() - started_at) * 1000),
        input_tokens=estimate_tokens('\n\n'.join(content for _, content in section_rows)),
        output_tokens=0,
        metadata={'sectionCount': exported_count, 'filename': filename},
    )
    return Response(
        content=docx_content,
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@app.get('/api/deals/{deal_id}/narratives/exports')
def list_narrative_export_versions(deal_id: int):
    get_deal_row_or_404(deal_id)
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT export_id, deal_id, filename, selected_draft_ids, section_count, created_at
                FROM narrative_export_versions
                WHERE deal_id = %s
                ORDER BY created_at DESC, export_id DESC;
                """,
                (deal_id,),
            )
            return [row_to_export_version(row) for row in cur.fetchall()]


@app.get('/api/deals/{deal_id}/narratives/exports/{export_id}/download')
def download_narrative_export_version(deal_id: int, export_id: int):
    get_deal_row_or_404(deal_id)
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM narrative_export_versions
                WHERE deal_id = %s AND export_id = %s;
                """,
                (deal_id, export_id),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail='Export version not found.')

    return Response(
        content=bytes(row['file_content']),
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={'Content-Disposition': f'attachment; filename="{row["filename"]}"'},
    )


@app.get('/api/deals/{deal_id}/narratives/{section_number}/drafts')
def list_narrative_drafts(deal_id: int, section_number: int):
    get_deal_row_or_404(deal_id)
    get_narrative_section_or_404(section_number)
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM narrative_drafts
                WHERE deal_id = %s AND section_number = %s
                ORDER BY created_at DESC, draft_id DESC;
                """,
                (deal_id, section_number),
            )
            return [row_to_narrative_draft(row) for row in cur.fetchall()]


@app.post('/api/deals/{deal_id}/narratives/{section_number}/drafts')
def save_narrative_edit(deal_id: int, section_number: int, payload: NarrativeEditRequest):
    deal = get_deal_row_or_404(deal_id)
    section = get_narrative_section_or_404(section_number)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            parent = None
            if payload.editedFromDraftId:
                cur.execute(
                    """
                    SELECT *
                    FROM narrative_drafts
                    WHERE draft_id = %s AND deal_id = %s AND section_number = %s;
                    """,
                    (payload.editedFromDraftId, deal_id, section_number),
                )
                parent = cur.fetchone()

            if not parent:
                cur.execute(
                    """
                    SELECT *
                    FROM narrative_drafts
                    WHERE deal_id = %s AND section_number = %s
                    ORDER BY created_at DESC, draft_id DESC
                    LIMIT 1;
                    """,
                    (deal_id, section_number),
                )
                parent = cur.fetchone()

    registry = resolve_mcp_registry_for_client(deal['legal_name'])
    registry_payload = {
        'client_match': parent['client_match'] if parent else (registry['client_match'] if registry else 'manual'),
        'mcp_url': parent['mcp_url'] if parent else (registry['mcp_url'] if registry else 'manual'),
    }
    generation_result = {
        'draft': payload.content,
        'model': parent['generation_model'] if parent else None,
        'agentId': parent['agent_id'] if parent else None,
        'conversationId': parent['conversation_id'] if parent else None,
    }
    discovered_sources = []
    if parent and parent['discovered_sources']:
        discovered_sources = [
            {
                'toolName': source.get('toolName', ''),
                'description': source.get('description', ''),
                'score': source.get('score', 0),
            }
            for source in parent['discovered_sources']
        ]

    row = store_narrative_draft(
        deal=deal,
        registry=registry_payload,
        section=section,
        discovered_sources=discovered_sources,
        custom_instructions=parent['custom_instructions'] if parent else '',
        output_template=parent['output_template'] if parent else '',
        generation_result=generation_result,
        version_type='edited',
        edited_from_draft_id=payload.editedFromDraftId or (parent['draft_id'] if parent else None),
        edited_by=payload.username or None,
    )
    return row_to_narrative_draft(row)


@app.delete('/api/deals/{deal_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_deal(deal_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM deals WHERE id = %s;', (deal_id,))
            deleted = cur.rowcount
            conn.commit()

    if deleted == 0:
        raise HTTPException(status_code=404, detail='Deal not found')

    return Response(status_code=status.HTTP_204_NO_CONTENT)
