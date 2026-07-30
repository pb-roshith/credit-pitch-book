import os
from contextlib import contextmanager

import psycopg
from dotenv import load_dotenv

from narrative_section_seed import seed_narrative_sections

load_dotenv()


DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'dbname': os.getenv('POSTGRES_DB', 'credit risk new version'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', 'root'),
}


@contextmanager
def get_connection():
    with psycopg.connect(**DB_CONFIG) as conn:
        yield conn


def init_db():
    create_users_table_sql = """
    CREATE TABLE IF NOT EXISTS app_users (
        user_id BIGSERIAL PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    create_deals_table_sql = """
    CREATE TABLE IF NOT EXISTS deals (
        id BIGSERIAL PRIMARY KEY,
        legal_name TEXT NOT NULL,
        industry TEXT NOT NULL,
        geography TEXT NOT NULL,
        customer_type TEXT NOT NULL,
        segment TEXT NOT NULL,
        kyc_status TEXT NOT NULL,
        facility TEXT NOT NULL,
        amount NUMERIC(18, 2) NOT NULL,
        pricing TEXT NOT NULL,
        collateral_required TEXT NOT NULL,
        currency TEXT NOT NULL,
        tenure TEXT NOT NULL,
        repayment TEXT NOT NULL,
        target_completion_date DATE NOT NULL,
        status TEXT NOT NULL DEFAULT 'Draft',
        progress INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    create_narrative_sections_table_sql = """
    CREATE TABLE IF NOT EXISTS narrative_sections (
        section_number INTEGER PRIMARY KEY,
        section_name TEXT NOT NULL,
        description TEXT NOT NULL,
        input_sources TEXT NOT NULL,
        expected_output TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    create_mcp_registry_table_sql = """
    CREATE TABLE IF NOT EXISTS mcp_client_registry (
        registry_id BIGSERIAL PRIMARY KEY,
        client_match TEXT NOT NULL UNIQUE,
        mcp_url TEXT NOT NULL,
        client_database TEXT,
        mistral_library_id TEXT,
        mistral_pdf_documents JSONB NOT NULL DEFAULT '[]'::jsonb,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    create_narrative_drafts_table_sql = """
    CREATE TABLE IF NOT EXISTS narrative_drafts (
        draft_id BIGSERIAL PRIMARY KEY,
        deal_id BIGINT NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
        section_number INTEGER NOT NULL REFERENCES narrative_sections(section_number) ON DELETE CASCADE,
        customer_name TEXT NOT NULL,
        client_match TEXT NOT NULL,
        mcp_url TEXT NOT NULL,
        input_sources TEXT NOT NULL,
        expected_output TEXT NOT NULL,
        custom_instructions TEXT,
        output_template TEXT,
        discovered_sources JSONB NOT NULL DEFAULT '[]'::jsonb,
        generated_output TEXT NOT NULL,
        generation_model TEXT,
        agent_id TEXT,
        conversation_id TEXT,
        otel_trace_id TEXT,
        source_discovery_agent_id TEXT,
        source_discovery_conversation_id TEXT,
        judge_id TEXT,
        judge_confidence_score NUMERIC(5, 2),
        judge_explanation TEXT,
        judge_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        version_type TEXT NOT NULL DEFAULT 'generated',
        edited_from_draft_id BIGINT REFERENCES narrative_drafts(draft_id) ON DELETE SET NULL,
        edited_by TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    create_narrative_export_versions_table_sql = """
    CREATE TABLE IF NOT EXISTS narrative_export_versions (
        export_id BIGSERIAL PRIMARY KEY,
        deal_id BIGINT NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
        filename TEXT NOT NULL,
        selected_draft_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
        section_count INTEGER NOT NULL DEFAULT 0,
        file_content BYTEA NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    create_ai_observability_events_table_sql = """
    CREATE TABLE IF NOT EXISTS ai_observability_events (
        event_id BIGSERIAL PRIMARY KEY,
        event_type TEXT NOT NULL,
        deal_id BIGINT REFERENCES deals(id) ON DELETE CASCADE,
        section_number INTEGER,
        draft_id BIGINT REFERENCES narrative_drafts(draft_id) ON DELETE SET NULL,
        model TEXT,
        status TEXT NOT NULL,
        latency_ms INTEGER,
        input_tokens INTEGER,
        output_tokens INTEGER,
        total_tokens INTEGER,
        estimated_cost NUMERIC(18, 6),
        error_message TEXT,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    create_otel_spans_table_sql = """
    CREATE TABLE IF NOT EXISTS otel_spans (
        span_row_id BIGSERIAL PRIMARY KEY,
        trace_id TEXT NOT NULL,
        span_id TEXT NOT NULL,
        parent_span_id TEXT,
        span_name TEXT NOT NULL,
        span_kind TEXT,
        status TEXT NOT NULL,
        status_message TEXT,
        start_time TIMESTAMPTZ NOT NULL,
        end_time TIMESTAMPTZ NOT NULL,
        duration_ms INTEGER NOT NULL,
        deal_id BIGINT REFERENCES deals(id) ON DELETE SET NULL,
        section_number INTEGER,
        draft_id BIGINT REFERENCES narrative_drafts(draft_id) ON DELETE SET NULL,
        workflow TEXT,
        attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (trace_id, span_id)
    );
    """
    with get_connection() as conn:
        conn.execute(create_users_table_sql)
        conn.execute(create_deals_table_sql)
        conn.execute(create_narrative_sections_table_sql)
        conn.execute(create_mcp_registry_table_sql)
        conn.execute(create_narrative_drafts_table_sql)
        conn.execute(create_narrative_export_versions_table_sql)
        conn.execute(create_ai_observability_events_table_sql)
        conn.execute(create_otel_spans_table_sql)
        seed_narrative_sections(conn)
        conn.execute("ALTER TABLE narrative_drafts ADD COLUMN IF NOT EXISTS version_type TEXT NOT NULL DEFAULT 'generated';")
        conn.execute("ALTER TABLE narrative_drafts ADD COLUMN IF NOT EXISTS edited_from_draft_id BIGINT REFERENCES narrative_drafts(draft_id) ON DELETE SET NULL;")
        conn.execute("ALTER TABLE narrative_drafts ADD COLUMN IF NOT EXISTS edited_by TEXT;")
        conn.execute("ALTER TABLE narrative_drafts ADD COLUMN IF NOT EXISTS judge_id TEXT;")
        conn.execute("ALTER TABLE narrative_drafts ADD COLUMN IF NOT EXISTS source_discovery_agent_id TEXT;")
        conn.execute("ALTER TABLE narrative_drafts ADD COLUMN IF NOT EXISTS source_discovery_conversation_id TEXT;")
        conn.execute("ALTER TABLE narrative_drafts ADD COLUMN IF NOT EXISTS otel_trace_id TEXT;")
        conn.execute("ALTER TABLE narrative_drafts ADD COLUMN IF NOT EXISTS judge_confidence_score NUMERIC(5, 2);")
        conn.execute("ALTER TABLE narrative_drafts ADD COLUMN IF NOT EXISTS judge_explanation TEXT;")
        conn.execute("ALTER TABLE narrative_drafts ADD COLUMN IF NOT EXISTS judge_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;")
        conn.execute("ALTER TABLE mcp_client_registry ADD COLUMN IF NOT EXISTS client_database TEXT;")
        conn.execute("ALTER TABLE mcp_client_registry ADD COLUMN IF NOT EXISTS mistral_library_id TEXT;")
        conn.execute("ALTER TABLE mcp_client_registry ADD COLUMN IF NOT EXISTS mistral_pdf_documents JSONB NOT NULL DEFAULT '[]'::jsonb;")
        conn.execute(
            """
            ALTER TABLE mcp_client_registry
            DROP COLUMN IF EXISTS client_key;
            """
        )
        conn.commit()
