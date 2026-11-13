from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from pgvector.psycopg import register_vector

from app.core.config import settings


@contextmanager
def connection():
    conn = psycopg.connect(
        settings.database_url,
        row_factory=dict_row,
        connect_timeout=5,
    )

    try:
        # Register the pgvector adapter on this exact connection.
        register_vector(conn)

        yield conn
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def init_db():
    # Ensure the extension exists before registering the vector adapter.
    with psycopg.connect(
        settings.database_url,
        connect_timeout=5,
    ) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.commit()

    with connection() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                id BIGSERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                source TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding vector(384) NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS purchase_orders (
                po_number TEXT PRIMARY KEY,
                supplier_id TEXT NOT NULL,
                company_code TEXT NOT NULL,
                amount NUMERIC(14,2) NOT NULL,
                currency TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """)

        c.execute("""
            CREATE OR REPLACE VIEW v_open_purchase_orders AS
            SELECT
                po_number,
                supplier_id,
                company_code,
                amount,
                currency,
                status,
                created_at
            FROM purchase_orders
            WHERE status IN ('OPEN', 'PENDING')
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS approvals (
                id UUID PRIMARY KEY,
                requester TEXT NOT NULL,
                action_type TEXT NOT NULL,
                payload JSONB NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now(),
                decided_at TIMESTAMPTZ,
                decided_by TEXT,
                result JSONB,
                idempotency_key TEXT UNIQUE
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id BIGSERIAL PRIMARY KEY,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                request_id TEXT,
                details JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """)

        c.execute("""
            INSERT INTO purchase_orders (
                po_number, supplier_id, company_code,
                amount, currency, status
            )
            VALUES
                ('4500001001', 'SUP-1001', 'IN01', 125000, 'INR', 'OPEN'),
                ('4500001002', 'SUP-1002', 'IN01', 87500, 'INR', 'PENDING'),
                ('4500001003', 'SUP-1003', 'IN02', 640000, 'INR', 'CLOSED')
            ON CONFLICT DO NOTHING
        """)