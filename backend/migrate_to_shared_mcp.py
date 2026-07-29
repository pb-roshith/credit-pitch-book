"""Move existing per-client MCP configuration into the shared MCP registry."""

import json

from database import init_db
from manufacture_data import (
    MCP_ROOT,
    db_name_for_client,
    load_existing_mistral_assets,
    register_backend_mcp,
    slugify,
)


def main():
    init_db()
    migrated = []
    for folder in sorted(MCP_ROOT.glob('*_mcp')):
        if folder.name in {'shared_mcp'}:
            continue
        client_slug = folder.name.removesuffix('_mcp')
        if client_slug in {'client_template', '__pycache__'}:
            continue
        library_id, documents = load_existing_mistral_assets(client_slug)
        if not library_id:
            continue
        client_name = client_slug.replace('_', ' ')
        register_backend_mcp(client_name, db_name_for_client(client_name), library_id, documents)
        migrated.append({'client': client_name, 'documents': len(documents), 'library': library_id})

    print(json.dumps(migrated, indent=2))


if __name__ == '__main__':
    main()
