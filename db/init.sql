CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id BIGSERIAL PRIMARY KEY, title TEXT NOT NULL, source TEXT NOT NULL,
  content TEXT NOT NULL, embedding vector(384) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx
  ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);
CREATE TABLE IF NOT EXISTS purchase_orders (
  po_number TEXT PRIMARY KEY, supplier_id TEXT NOT NULL, company_code TEXT NOT NULL,
  amount NUMERIC(14,2) NOT NULL, currency TEXT NOT NULL, status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE OR REPLACE VIEW v_open_purchase_orders AS
  SELECT po_number, supplier_id, company_code, amount, currency, status, created_at
  FROM purchase_orders WHERE status IN ('OPEN','PENDING');
CREATE TABLE IF NOT EXISTS approvals (
  id UUID PRIMARY KEY, requester TEXT NOT NULL, action_type TEXT NOT NULL,
  payload JSONB NOT NULL, status TEXT NOT NULL CHECK(status IN ('PENDING','APPROVED','REJECTED','EXECUTED','FAILED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), decided_at TIMESTAMPTZ,
  decided_by TEXT, result JSONB, idempotency_key TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS audit_events (
  id BIGSERIAL PRIMARY KEY, event_type TEXT NOT NULL, actor TEXT NOT NULL,
  request_id TEXT, details JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO purchase_orders(po_number,supplier_id,company_code,amount,currency,status) VALUES
('4500001001','SUP-1001','IN01',125000,'INR','OPEN'),
('4500001002','SUP-1002','IN01',87500,'INR','PENDING'),
('4500001003','SUP-1003','IN02',640000,'INR','CLOSED')
ON CONFLICT DO NOTHING;
