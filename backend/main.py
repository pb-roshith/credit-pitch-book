from decimal import Decimal
import hashlib
import hmac
from html import escape
from io import BytesIO
import json
import os
import re
import secrets
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from mistralai.client import Mistral
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from database import get_connection, init_db
from manufacture_data import manufacture_client_data
from mcp_client import call_mcp_tool, list_mcp_tools


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
        'judge': {
            'judgeId': row['judge_id'],
            'confidenceScore': float(row['judge_confidence_score']) if row['judge_confidence_score'] is not None else None,
            'confidencePercent': round(float(row['judge_confidence_score']) * 100) if row['judge_confidence_score'] is not None else None,
            'explanation': row['judge_explanation'],
            'metadata': row['judge_metadata'] or {},
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


def run_source_discovery_agent(client, tools, section):
    model = os.getenv('MISTRAL_GENERATION_MODEL', 'mistral-large-latest')
    expanded_input_sources = [
        {
            'source': source,
            'aliases': source_aliases(source),
            'broadScope': is_broad_source(source),
        }
        for source in parse_input_sources(section['input_sources'])
    ]
    agent = client.beta.agents.create(
        model=model,
        name='Credit Pitch Book Source Discovery',
        instructions=(
            'You are a source discovery agent for a credit pitch book. '
            'Choose only MCP tools from the provided list that are relevant to the requested narrative section. '
            'Use narrative_sections.input_sources as the allowed source scope and narrative_sections.expected_output as the output target. '
            'Return only JSON in this exact shape: {"toolNames":["tool_name"]}.'
        ),
        completion_args={
            'temperature': 0.0,
            'max_tokens': 600,
            'response_format': {'type': 'json_object'},
        },
    )
    prompt = {
        'sectionNumber': section['section_number'],
        'sectionName': section['section_name'],
        'description': section['description'],
        'inputSources': section['input_sources'],
        'expandedInputSources': expanded_input_sources,
        'expectedOutput': section['expected_output'],
        'availableTools': [
            {
                'name': tool['name'],
                'description': tool.get('description', ''),
            }
            for tool in tools
        ],
        'selectionRules': [
            'Select only tools that map to the inputSources and description.',
            'Prefer precise document content tools over generic registry or database tools.',
            'Return 1 to 5 tool names.',
        ],
    }
    response = client.beta.conversations.start(
        agent_id=agent.id,
        inputs=json.dumps(prompt),
        store=False,
    )
    selected_tool_names = parse_agent_tool_selection(extract_beta_conversation_text(response), tools)
    return selected_tool_names, agent.id, response.conversation_id


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
    if api_key:
        client = Mistral(api_key=api_key)
        selected_tool_names, agent_id, conversation_id = run_source_discovery_agent(client, tools, section)

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
    version_type='generated',
    edited_from_draft_id=None,
    edited_by=None,
):
    query = """
        INSERT INTO narrative_drafts (
            deal_id, section_number, customer_name, client_match, mcp_url,
            input_sources, expected_output, custom_instructions, output_template,
            discovered_sources, generated_output, generation_model, agent_id, conversation_id,
            judge_id, judge_confidence_score, judge_explanation, judge_metadata,
            version_type, edited_from_draft_id, edited_by
        )
        VALUES (
            %(deal_id)s, %(section_number)s, %(customer_name)s, %(client_match)s, %(mcp_url)s,
            %(input_sources)s, %(expected_output)s, %(custom_instructions)s, %(output_template)s,
            %(discovered_sources)s::jsonb, %(generated_output)s, %(generation_model)s, %(agent_id)s, %(conversation_id)s,
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
    discovery = await discover_sources(registry, section)
    generation_result = generate_narrative_text(
        deal=deal,
        section=section,
        discovered_sources=discovery['selectedSources'],
        custom_instructions=payload.customInstructions,
        output_template=payload.outputTemplate,
    )
    draft_row = store_narrative_draft(
        deal=deal,
        registry=registry,
        section=section,
        discovered_sources=discovery['selectedSources'],
        custom_instructions=payload.customInstructions,
        output_template=payload.outputTemplate,
        generation_result=generation_result,
        edited_by=payload.username or None,
    )
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

    judge_result = judge_narrative_relevance(
        deal=deal,
        section=section,
        discovered_sources=discovered_sources,
        draft=draft_row['generated_output'],
    )

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

    return row_to_narrative_draft(updated_row)


@app.post('/api/deals/{deal_id}/narratives/export')
def export_narrative_drafts(deal_id: int, payload: NarrativeExportRequest):
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
