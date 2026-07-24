import json
from functools import lru_cache

from fastapi import HTTPException
from mistralai.client import Mistral


NARRATIVE_DRAFTER_INSTRUCTIONS = (
    'You write concise, evidence-grounded corporate credit narratives. '
    'Use only discovered source content. If a detail is not supported by sources, do not invent it. '
    'Add inline citations for material facts using the exact source label format [Source: source_name]. '
    'Use the SOURCE labels provided in discoveredSourceContent as source_name values. '
    'Every paragraph or bullet that uses source data must include at least one inline citation. '
    'Respect custom instructions and output template when provided. Return only the narrative content.'
)
NARRATIVE_DRAFTER_AGENT_NAME = 'Credit Pitch Book Narrative Drafter'


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


@lru_cache(maxsize=8)
def _get_narrative_agent(api_key, model):
    client = Mistral(api_key=api_key)
    existing_agents = client.beta.agents.list(name=NARRATIVE_DRAFTER_AGENT_NAME, page_size=20)
    agent = next((item for item in existing_agents if item.name == NARRATIVE_DRAFTER_AGENT_NAME), None)
    if not agent:
        agent = client.beta.agents.create(
            model=model,
            name=NARRATIVE_DRAFTER_AGENT_NAME,
            instructions=NARRATIVE_DRAFTER_INSTRUCTIONS,
            completion_args={'temperature': 0.2, 'max_tokens': 2500},
        )
    return client, agent


def generate_narrative(api_key, model, deal, section, discovered_sources, custom_instructions, output_template):
    """Generate a narrative using one cached Mistral beta drafting agent."""
    context = '\n\n'.join(
        f"SOURCE: {source['toolName']}\n{source['text']}"
        for source in discovered_sources
    )
    if not context.strip():
        raise HTTPException(status_code=422, detail='No relevant MCP source content was discovered.')

    if not api_key:
        return {
            'draft': (
                f"# {section['section_name']}\n\n"
                'Draft source material was discovered, but MISTRAL_API_KEY is not configured for AI generation.\n\n'
                f'{context[:4000]}'
            ),
            'agentId': None,
            'conversationId': None,
            'model': None,
        }

    client, agent = _get_narrative_agent(api_key, model)
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
    draft = extract_conversation_text(response)
    if not draft:
        raise HTTPException(status_code=502, detail='Mistral beta agent returned an empty draft.')
    return {
        'draft': draft,
        'agentId': agent.id,
        'conversationId': response.conversation_id,
        'model': model,
    }
