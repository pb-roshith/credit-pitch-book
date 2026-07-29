from database import ensure_database, get_connection


CLIENT_ID = 1001


def create_support_clients_table(conn):
    conn.execute('CREATE SCHEMA IF NOT EXISTS credit_dossier;')
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS credit_dossier.clients (
            client_id BIGINT PRIMARY KEY,
            client_name TEXT NOT NULL
        );
        """
    )
    conn.execute(
        """
        INSERT INTO credit_dossier.clients (client_id, client_name)
        VALUES (%s, %s)
        ON CONFLICT (client_id) DO UPDATE SET client_name = EXCLUDED.client_name;
        """,
        (CLIENT_ID, 'Aster Auto Components Limited'),
    )


def create_section2_tables(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS credit_dossier.section2_customer_information (
            client_id BIGINT PRIMARY KEY REFERENCES credit_dossier.clients(client_id) ON DELETE CASCADE,
            business_activities TEXT NOT NULL,
            business_since TEXT,
            relationship_status TEXT,
            regulator_enquiry_date DATE,
            regulator_enquiry_note TEXT,
            current_rating_moodys TEXT,
            current_rating_date DATE,
            current_rating_note TEXT,
            previous_rating_moodys TEXT,
            previous_rating_date DATE,
            previous_rating_note TEXT,
            bank_internal_rating TEXT,
            blacklisted BOOLEAN,
            blacklisted_note TEXT,
            related_party_status TEXT,
            related_party_type TEXT,
            politically_exposed_person BOOLEAN,
            pep_note TEXT,
            present_in_defaulter_list BOOLEAN,
            defaulter_list_note TEXT,
            source_document TEXT NOT NULL,
            source_pdf_pages INTEGER[] NOT NULL,
            prepared_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS credit_dossier.section2_ownership_structure (
            ownership_id BIGSERIAL PRIMARY KEY,
            client_id BIGINT NOT NULL REFERENCES credit_dossier.clients(client_id) ON DELETE CASCADE,
            owner_details TEXT NOT NULL,
            capital_amount_gbp NUMERIC(18, 2),
            ownership_percent NUMERIC(7, 4) NOT NULL,
            source_note TEXT,
            source_document TEXT NOT NULL,
            source_pdf_pages INTEGER[] NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (client_id, owner_details)
        );
        """
    )


def seed_customer_information(conn):
    conn.execute(
        """
        INSERT INTO credit_dossier.section2_customer_information (
            client_id,
            business_activities,
            business_since,
            relationship_status,
            regulator_enquiry_date,
            regulator_enquiry_note,
            current_rating_moodys,
            current_rating_date,
            current_rating_note,
            previous_rating_moodys,
            previous_rating_date,
            previous_rating_note,
            bank_internal_rating,
            blacklisted,
            blacklisted_note,
            related_party_status,
            related_party_type,
            politically_exposed_person,
            pep_note,
            present_in_defaulter_list,
            defaulter_list_note,
            source_document,
            source_pdf_pages
        )
        VALUES (
            %(client_id)s,
            %(business_activities)s,
            %(business_since)s,
            %(relationship_status)s,
            %(regulator_enquiry_date)s,
            %(regulator_enquiry_note)s,
            %(current_rating_moodys)s,
            %(current_rating_date)s,
            %(current_rating_note)s,
            %(previous_rating_moodys)s,
            %(previous_rating_date)s,
            %(previous_rating_note)s,
            %(bank_internal_rating)s,
            %(blacklisted)s,
            %(blacklisted_note)s,
            %(related_party_status)s,
            %(related_party_type)s,
            %(politically_exposed_person)s,
            %(pep_note)s,
            %(present_in_defaulter_list)s,
            %(defaulter_list_note)s,
            %(source_document)s,
            %(source_pdf_pages)s
        )
        ON CONFLICT (client_id) DO UPDATE SET
            business_activities = EXCLUDED.business_activities,
            business_since = EXCLUDED.business_since,
            relationship_status = EXCLUDED.relationship_status,
            regulator_enquiry_date = EXCLUDED.regulator_enquiry_date,
            regulator_enquiry_note = EXCLUDED.regulator_enquiry_note,
            current_rating_moodys = EXCLUDED.current_rating_moodys,
            current_rating_date = EXCLUDED.current_rating_date,
            current_rating_note = EXCLUDED.current_rating_note,
            previous_rating_moodys = EXCLUDED.previous_rating_moodys,
            previous_rating_date = EXCLUDED.previous_rating_date,
            previous_rating_note = EXCLUDED.previous_rating_note,
            bank_internal_rating = EXCLUDED.bank_internal_rating,
            blacklisted = EXCLUDED.blacklisted,
            blacklisted_note = EXCLUDED.blacklisted_note,
            related_party_status = EXCLUDED.related_party_status,
            related_party_type = EXCLUDED.related_party_type,
            politically_exposed_person = EXCLUDED.politically_exposed_person,
            pep_note = EXCLUDED.pep_note,
            present_in_defaulter_list = EXCLUDED.present_in_defaulter_list,
            defaulter_list_note = EXCLUDED.defaulter_list_note,
            source_document = EXCLUDED.source_document,
            source_pdf_pages = EXCLUDED.source_pdf_pages;
        """,
        {
            'client_id': CLIENT_ID,
            'business_activities': (
                'Manufacturing and export of precision auto components, CNC-machined assemblies, '
                'forged parts, and tooling supplied to domestic OEMs and European industrial customers.'
            ),
            'business_since': '2012',
            'relationship_status': 'Existing banking relationship with active working capital and term loan exposure',
            'regulator_enquiry_date': '2025-11-18',
            'regulator_enquiry_note': 'No open regulatory enquiry identified in the latest diligence review.',
            'current_rating_moodys': 'Baa3 Stable',
            'current_rating_date': '2026-03-31',
            'current_rating_note': 'Rating reflects stable operating cash flows and moderate leverage.',
            'previous_rating_moodys': 'Ba1 Positive',
            'previous_rating_date': '2025-03-31',
            'previous_rating_note': 'Prior rating constrained by elevated working capital intensity.',
            'bank_internal_rating': 'A-/Watch Neutral',
            'blacklisted': False,
            'blacklisted_note': 'No blacklisting record found in bank screening and external watchlist checks.',
            'related_party_status': 'Related parties identified and disclosed',
            'related_party_type': 'Promoter-controlled supplier and leasing affiliate',
            'politically_exposed_person': False,
            'pep_note': 'No promoter, director, or beneficial owner identified as PEP.',
            'present_in_defaulter_list': False,
            'defaulter_list_note': 'Not present in defaulter lists reviewed as part of onboarding refresh.',
            'source_document': 'Mistral PDF Library 019f561a-b2e6-7552-b9fe-1215aec0f20c',
            'source_pdf_pages': [12, 13, 14],
        },
    )


def seed_ownership_structure(conn):
    rows = [
        (
            CLIENT_ID,
            'Aster Holdings Private Limited - promoter holding company',
            '12500000.00',
            '52.5000',
            'Controlling shareholder with board nomination rights.',
            'Mistral PDF Library 019f561a-b2e6-7552-b9fe-1215aec0f20c',
            [15, 16],
        ),
        (
            CLIENT_ID,
            'Meera Shah Family Trust',
            '4200000.00',
            '17.6500',
            'Promoter family trust holding ordinary equity shares.',
            'Mistral PDF Library 019f561a-b2e6-7552-b9fe-1215aec0f20c',
            [16],
        ),
        (
            CLIENT_ID,
            'Rahul Shah',
            '2800000.00',
            '11.7500',
            'Managing director and individual promoter shareholder.',
            'Mistral PDF Library 019f561a-b2e6-7552-b9fe-1215aec0f20c',
            [16, 17],
        ),
        (
            CLIENT_ID,
            'Northbridge Growth Fund II',
            '3000000.00',
            '12.6000',
            'Minority institutional investor with no day-to-day control.',
            'Mistral PDF Library 019f561a-b2e6-7552-b9fe-1215aec0f20c',
            [17],
        ),
        (
            CLIENT_ID,
            'Employee Stock Option Trust',
            '1309523.81',
            '5.5000',
            'Employee benefit trust for vested and unvested ESOP pool.',
            'Mistral PDF Library 019f561a-b2e6-7552-b9fe-1215aec0f20c',
            [17, 18],
        ),
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO credit_dossier.section2_ownership_structure (
                client_id,
                owner_details,
                capital_amount_gbp,
                ownership_percent,
                source_note,
                source_document,
                source_pdf_pages
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (client_id, owner_details) DO UPDATE SET
                capital_amount_gbp = EXCLUDED.capital_amount_gbp,
                ownership_percent = EXCLUDED.ownership_percent,
                source_note = EXCLUDED.source_note,
                source_document = EXCLUDED.source_document,
                source_pdf_pages = EXCLUDED.source_pdf_pages;
            """,
            rows,
        )


def load_section2_tables():
    ensure_database()
    with get_connection() as conn:
        create_support_clients_table(conn)
        create_section2_tables(conn)
        seed_customer_information(conn)
        seed_ownership_structure(conn)
        conn.commit()


if __name__ == '__main__':
    load_section2_tables()
    print('Loaded section2_customer_information and section2_ownership_structure.')
