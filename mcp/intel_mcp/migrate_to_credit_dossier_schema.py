from psycopg import sql

from database import ensure_database, get_connection


TABLES_TO_MOVE = (
    'credit_balance_sheet',
    'credit_cashflow_statement',
    'credit_income_statement',
    'credit_bank_statements',
    'credit_net_worth_statement',
    'credit_projected_financials',
    'section2_customer_information',
    'section2_ownership_structure',
)


def table_exists(conn, schema_name, table_name):
    return bool(
        conn.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s;
            """,
            (schema_name, table_name),
        ).fetchone()
    )


def migrate_to_credit_dossier_schema():
    ensure_database()
    moved = []
    skipped = []
    with get_connection() as conn:
        conn.execute('CREATE SCHEMA IF NOT EXISTS credit_dossier;')
        for table_name in TABLES_TO_MOVE:
            public_exists = table_exists(conn, 'public', table_name)
            target_exists = table_exists(conn, 'credit_dossier', table_name)

            if public_exists and target_exists:
                raise RuntimeError(
                    f'Both public.{table_name} and credit_dossier.{table_name} exist. '
                    'Resolve the duplicate manually before migration.'
                )

            if public_exists:
                conn.execute(
                    sql.SQL('ALTER TABLE {} SET SCHEMA {};').format(
                        sql.Identifier('public', table_name),
                        sql.Identifier('credit_dossier'),
                    )
                )
                moved.append(table_name)
            else:
                skipped.append(table_name)

        conn.commit()

    return {'moved': moved, 'skipped': skipped}


if __name__ == '__main__':
    result = migrate_to_credit_dossier_schema()
    print(f'Moved to credit_dossier: {result["moved"]}')
    print(f'Skipped because not found in public: {result["skipped"]}')
