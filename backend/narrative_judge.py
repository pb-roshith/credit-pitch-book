import re
import time
from functools import lru_cache

from mistralai.client import Mistral


JUDGE_INSTRUCTIONS = (
    'You are a credit risk narrative relevance judge. Compare the generated narrative against the data sources. '
    'The conversation you judge contains a user message with the discovered data sources and the section requirements, '
    'followed by an assistant message containing the generated narrative. Judge the assistant message against the sources. '
    'Return a numeric score from 0 to 1. Score only source groundedness and relevance for this exact section. '
    'Do not use generic examples, reusable boilerplate, or facts that are not present in the supplied sources or generated narrative. '
    'Calibrate strictly: do not return 1.00. Use 0.99 as the maximum because source support cannot be independently proven for every claim by this evaluation alone. '
    'Every material claim must be directly supported by supplied sources, '
    'all important source-derived claims are cited, and the expected output is fully addressed. '
    'Use 0.90-0.99 for strong drafts with small citation or coverage gaps. '
    'Use 0.75-0.89 for useful drafts with partial source coverage, weak support for some conclusions, or missing expected-output items. '
    'Use below 0.75 when unsupported claims, irrelevant content, or hallucination risk is material. '
    'If any material claim is not traceable to a source, do not score above 0.90. '
    'If the narrative only covers part of the expected output, do not score above 0.85. '
    'If citations are missing or too broad for several claims, do not score above 0.88. '
    'Format analysis exactly with these two headings and bullet points: '
    'SCORE EXPLANATION: explain the evidence and coverage that justify the awarded score. '
    'REMAINING GAP EXPLANATION: explain the unsupported, weak, or missing items that account for 1 minus the score. '
    'Each bullet must mention a specific narrative claim and the exact supporting, partial, or missing source label. '
    'Even for a 0.99 score, name the small remaining verification limitation under remaining gaps. '
    'Do not invent revenue, EBITDA, market share, customer base, or operational metrics unless they appear in the supplied content.'
)
NARRATIVE_JUDGE_NAME = 'Credit Pitch Book Narrative Relevance Judge'
JUDGE_DESCRIPTION = 'Scores whether a credit narrative is grounded in discovered MCP data sources.'
JUDGE_OUTPUT = {
    'type': 'REGRESSION',
    'min': 0,
    'max': 1,
    'min_description': 'The narrative is unsupported by the source data or contains material hallucinations.',
    'max_description': 'The narrative is fully supported by the source data with no material hallucinations.',
}


@lru_cache(maxsize=8)
def _get_judge(api_key, model):
    client = Mistral(api_key=api_key)
    listed_judges = client.beta.observability.judges.list(q=NARRATIVE_JUDGE_NAME, page_size=50)
    judge = next(
        (
            item for item in (listed_judges.judges.results or [])
            if item.name == NARRATIVE_JUDGE_NAME
        ),
        None,
    )
    if judge:
        judge = client.beta.observability.judges.fetch(judge_id=judge.id)
        if judge.instructions != JUDGE_INSTRUCTIONS or judge.model_name != model:
            # Reuse the existing judge while keeping its scoring instructions current.
            client.beta.observability.judges.update(
                judge_id=judge.id,
                name=NARRATIVE_JUDGE_NAME,
                description=JUDGE_DESCRIPTION,
                model_name=model,
                output=JUDGE_OUTPUT,
                instructions=JUDGE_INSTRUCTIONS,
                tools=[],
            )
            judge = client.beta.observability.judges.fetch(judge_id=judge.id)
    else:
        judge = client.beta.observability.judges.create(
            name=NARRATIVE_JUDGE_NAME,
            description=JUDGE_DESCRIPTION,
            model_name=model,
            output=JUDGE_OUTPUT,
            instructions=JUDGE_INSTRUCTIONS,
            tools=[],
        )
    return client, judge


def split_explanations(analysis):
    text = (analysis or '').strip()
    score_match = re.search(
        r'SCORE\s+EXPLANATION\s*:?[\s\S]*?(?=REMAINING\s+GAP\s+EXPLANATION\s*:|$)',
        text,
        re.IGNORECASE,
    )
    gap_match = re.search(
        r'REMAINING\s+GAP\s+EXPLANATION\s*:?[\s\S]*$',
        text,
        re.IGNORECASE,
    )
    score_explanation = score_match.group(0) if score_match else ''
    remaining_gap_explanation = gap_match.group(0) if gap_match else text
    score_explanation = re.sub(r'^SCORE\s+EXPLANATION\s*:?\s*', '', score_explanation, flags=re.IGNORECASE).strip()
    remaining_gap_explanation = re.sub(
        r'^REMAINING\s+GAP\s+EXPLANATION\s*:?\s*',
        '',
        remaining_gap_explanation,
        flags=re.IGNORECASE,
    ).strip()
    return score_explanation, remaining_gap_explanation


def citation_calibration_ceiling(draft, source_labels):
    """Apply a transparent citation-coverage ceiling to an LLM judge score."""
    material_paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r'\n\s*\n', draft)
        if paragraph.strip() and not paragraph.lstrip().startswith('#')
    ]
    if not material_paragraphs:
        return 0.60, {'materialParagraphs': 0, 'citedParagraphs': 0, 'validCitationCount': 0}

    valid_labels = {label.strip().lower() for label in source_labels}
    citation_pattern = re.compile(r'\[Source:\s*([^\]]+)\]', re.IGNORECASE)
    cited_paragraphs = 0
    cited_labels = set()
    for paragraph in material_paragraphs:
        labels = {match.strip().lower() for match in citation_pattern.findall(paragraph)}
        valid_matches = labels & valid_labels
        if valid_matches:
            cited_paragraphs += 1
            cited_labels.update(valid_matches)

    paragraph_coverage = cited_paragraphs / len(material_paragraphs)
    expected_source_count = max(1, min(len(valid_labels), 3))
    source_coverage = min(1, len(cited_labels) / expected_source_count)
    ceiling = min(0.99, 0.72 + (0.18 * paragraph_coverage) + (0.09 * source_coverage))
    return ceiling, {
        'materialParagraphs': len(material_paragraphs),
        'citedParagraphs': cited_paragraphs,
        'validCitationCount': len(cited_labels),
        'paragraphCoveragePercent': round(paragraph_coverage * 100),
        'sourceCoveragePercent': round(source_coverage * 100),
    }


def judge_conversation_with_retry(client, judge_id, messages, properties, attempts=3):
    """Retry transient Mistral Judge failures without creating another judge."""
    for attempt in range(attempts):
        try:
            return client.beta.observability.judges.judge_conversation(
                judge_id=judge_id,
                messages=messages,
                properties=properties,
            )
        except Exception as exc:
            retryable = any(code in str(exc) for code in ('429', '500', '502', '503', '504'))
            if not retryable or attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt)


def judge_narrative(api_key, model, deal, section, discovered_sources, draft):
    """Evaluate a draft with one cached Mistral observability judge."""
    if not api_key:
        return None
    source_context = '\n\n'.join(
        f"SOURCE: {source['toolName']}\n{source['text']}"
        for source in discovered_sources
    )
    source_labels = [source['toolName'] for source in discovered_sources]
    if not source_context.strip() or not draft.strip():
        return None

    client, judge = _get_judge(api_key, model)
    try:
        result = judge_conversation_with_retry(
            client=client,
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
                        'Discovered data sources:\n'
                        f'{source_context[:30000]}\n\n'
                        'Judge only the next assistant message. Explain both what supports the awarded score and what accounts for the remaining gap. '
                        'Use the two required headings and bullet points. Never award 1.00; use 0.99 as the highest score. '
                        'Apply strict score caps: unsupported material claim max 0.90; '
                        'partial expected-output coverage max 0.85; missing or broad citations across several claims max 0.88.'
                    ),
                },
                {'role': 'assistant', 'content': draft[:12000]},
            ],
            properties={
                'client': deal['legal_name'],
                'section_number': section['section_number'],
                'section_name': section['section_name'],
                'data_sources': source_context[:30000],
                'generated_narrative': draft[:12000],
            },
        )
        raw_score = max(0, min(1, float(result.answer)))
        citation_ceiling, citation_summary = citation_calibration_ceiling(draft, source_labels)
        score = min(raw_score, citation_ceiling)
        score_explanation, remaining_gap_explanation = split_explanations(result.analysis)
        citation_summary_line = (
            f"- Citation coverage check: {citation_summary['citedParagraphs']} of "
            f"{citation_summary['materialParagraphs']} material paragraphs cite an available source; "
            f"{citation_summary['validCitationCount']} source label(s) were used."
        )
        score_explanation = '\n'.join(part for part in [score_explanation, citation_summary_line] if part)
        if score < raw_score:
            calibration_gap = (
                f"- The score was capped at {round(score * 100)}% because citation coverage was "
                f"{citation_summary['paragraphCoveragePercent']}% across material paragraphs and "
                f"{citation_summary['sourceCoveragePercent']}% across available source labels."
            )
            remaining_gap_explanation = '\n'.join(
                part for part in [remaining_gap_explanation, calibration_gap] if part
            )
        return {
            'judgeId': judge.id,
            'confidenceScore': score,
            'confidencePercent': round(score * 100),
            'explanation': result.analysis,
            'scoreExplanation': score_explanation,
            'remainingGapExplanation': remaining_gap_explanation,
            'metadata': {
                'model': model,
                'answer': result.answer,
                'rawScore': raw_score,
                'citationCalibrationCeiling': citation_ceiling,
                'citationSummary': citation_summary,
                'scoreExplanation': score_explanation,
                'remainingGapExplanation': remaining_gap_explanation,
            },
        }
    except Exception as exc:
        return {
            'judgeId': None,
            'confidenceScore': None,
            'confidencePercent': None,
            'explanation': f'Judge evaluation could not be completed: {exc}',
            'scoreExplanation': '',
            'remainingGapExplanation': f'Judge evaluation could not be completed: {exc}',
            'metadata': {'error': str(exc), 'model': model},
        }
