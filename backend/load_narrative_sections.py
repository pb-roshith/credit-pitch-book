import re
import sys

from database import get_connection, init_db
from extract_docx_tables import extract_tables


HEADER = ['Section', 'Description', 'Input Sources', 'Expected Output (GenAI/Automation)']


def parse_section(value):
    match = re.match(r'^\s*(\d+)\.\s*(.+?)\s*$', value)
    if not match:
        raise ValueError(f'Could not parse section value: {value}')
    section_name = re.sub(r'\s*\([^)]*\)', '', match.group(2)).strip()
    return int(match.group(1)), section_name


def find_automation_scope_table(path):
    for table in extract_tables(path):
        if not table:
            continue
        normalized_header = [cell.strip() for cell in table[0]]
        if normalized_header == HEADER and len(table) >= 17:
            return table
    raise ValueError('Could not find the 16-section automation scope table.')


def load_sections(path):
    init_db()
    table = find_automation_scope_table(path)
    rows = []
    for source_row in table[1:17]:
        section_number, section_name = parse_section(source_row[0])
        rows.append(
            {
                'section_number': section_number,
                'section_name': section_name,
                'description': source_row[1],
                'input_sources': source_row[2],
                'expected_output': source_row[3],
            }
        )

    query = """
        INSERT INTO narrative_sections (
            section_number, section_name, description, input_sources, expected_output
        )
        VALUES (
            %(section_number)s, %(section_name)s, %(description)s, %(input_sources)s, %(expected_output)s
        )
        ON CONFLICT (section_number) DO UPDATE SET
            section_name = EXCLUDED.section_name,
            description = EXCLUDED.description,
            input_sources = EXCLUDED.input_sources,
            expected_output = EXCLUDED.expected_output,
            updated_at = NOW();
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(query, rows)
            conn.commit()
    return len(rows)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python load_narrative_sections.py <docx_path>')

    loaded = load_sections(sys.argv[1])
    print(f'Loaded {loaded} narrative sections.')
