import sys
import zipfile
import xml.etree.ElementTree as ET


NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


def cell_text(cell):
    parts = []
    for node in cell.findall('.//w:t', NS):
        if node.text:
            parts.append(node.text)
    return ' '.join(' '.join(parts).split())


def extract_tables(path):
    with zipfile.ZipFile(path) as docx:
        xml = docx.read('word/document.xml')
    root = ET.fromstring(xml)
    tables = []
    for table in root.findall('.//w:tbl', NS):
        rows = []
        for row in table.findall('./w:tr', NS):
            rows.append([cell_text(cell) for cell in row.findall('./w:tc', NS)])
        tables.append(rows)
    return tables


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python extract_docx_tables.py <docx_path>')

    for index, table in enumerate(extract_tables(sys.argv[1]), start=1):
        print(f'TABLE {index}')
        for row in table:
            print(' | '.join(row))
        print()
