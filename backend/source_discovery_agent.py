import json
import re
from functools import lru_cache

from mistralai.client import Mistral


SOURCE_DISCOVERY_INSTRUCTIONS = (
    'You are a source discovery agent for a credit pitch book. '
    'Choose only MCP tools from the provided list that are relevant to the requested narrative section. '
    'Use narrative_sections.input_sources as the allowed source scope and narrative_sections.expected_output as the output target. '
    'Return only JSON in this exact shape: {"toolNames":["tool_name"]}.'
)
SOURCE_DISCOVERY_AGENT_NAME = 'Credit Pitch Book Source Discovery'


def estimate_tokens(text):
    if not text:
        return 0
    return max(1, round(len(str(text)) / 4))


def extract_conversation_text(response):
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


def parse_tool_selection(agent_text, tools):
    valid_tool_names = {tool['name'] for tool in tools}
    candidates = []
    try:
        candidates.append(json.loads(agent_text))
    except json.JSONDecodeError:
        pass

    json_match = re.search(r'(\{.*\}|\[.*\])', agent_text, re.DOTALL)
    if json_match:
        try:
            candidates.append(json.loads(json_match.group(1)))
        except json.JSONDecodeError:
            pass

    for candidate in candidates:
        selected = (
            candidate.get('toolNames') or candidate.get('tools') or candidate.get('selectedTools') or []
            if isinstance(candidate, dict)
            else candidate
        )
        if isinstance(selected, list):
            tool_names = [name for name in selected if isinstance(name, str) and name in valid_tool_names]
            if tool_names:
                return tool_names
    return []


@lru_cache(maxsize=8)
def _get_source_discovery_agent(api_key, model):
    client = Mistral(api_key=api_key)
    existing_agents = client.beta.agents.list(name=SOURCE_DISCOVERY_AGENT_NAME, page_size=20)
    agent = next((item for item in existing_agents if item.name == SOURCE_DISCOVERY_AGENT_NAME), None)
    if not agent:
        agent = client.beta.agents.create(
            model=model,
            name=SOURCE_DISCOVERY_AGENT_NAME,
            instructions=SOURCE_DISCOVERY_INSTRUCTIONS,
            completion_args={
                'temperature': 0.0,
                'max_tokens': 600,
                'response_format': {'type': 'json_object'},
            },
        )
    return client, agent


def select_source_tools(api_key, model, section, expanded_input_sources, tools):
    """Use one cached Mistral beta agent to select MCP tools for a section."""
    client, agent = _get_source_discovery_agent(api_key, model)
    prompt = {
        'sectionNumber': section['section_number'],
        'sectionName': section['section_name'],
        'description': section['description'],
        'inputSources': section['input_sources'],
        'expandedInputSources': expanded_input_sources,
        'expectedOutput': section['expected_output'],
        'availableTools': [
            {'name': tool['name'], 'description': tool.get('description', '')}
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
    response_text = extract_conversation_text(response)
    return {
        'toolNames': parse_tool_selection(response_text, tools),
        'agentId': agent.id,
        'conversationId': response.conversation_id,
        'inputTokens': estimate_tokens(SOURCE_DISCOVERY_INSTRUCTIONS) + estimate_tokens(json.dumps(prompt)),
        'outputTokens': estimate_tokens(response_text),
        'tokenUsageEstimated': True,
    }
