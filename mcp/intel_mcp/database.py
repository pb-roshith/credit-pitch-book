import os
from contextlib import contextmanager

import psycopg
from dotenv import load_dotenv


load_dotenv()


DEFAULT_DB = 'postgres'
INTEL_MCP_DB = os.getenv('INTEL_MCP_DB', 'intel_mcp_db')


def base_config(dbname=INTEL_MCP_DB):
    return {
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': os.getenv('POSTGRES_PORT', '5432'),
        'dbname': dbname,
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD', 'root'),
    }


@contextmanager
def get_connection(dbname=INTEL_MCP_DB):
    with psycopg.connect(**base_config(dbname)) as conn:
        yield conn


def ensure_database():
    with psycopg.connect(**base_config(DEFAULT_DB), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM pg_database WHERE datname = %s;', (INTEL_MCP_DB,))
            if cur.fetchone():
                return False
            cur.execute(f'CREATE DATABASE "{INTEL_MCP_DB}"')
            return True
