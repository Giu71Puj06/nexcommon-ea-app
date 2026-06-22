create table if not exists public.ea_runs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  matricola text,
  lotto text,
  data_prova text,
  pressione_inizio_bar numeric,
  pressione_fine_bar numeric,
  gamma_max numeric,
  classe text,
  raw_summary jsonb
);

-- Creare manualmente in Supabase Storage un bucket privato chiamato: ea-prove
-- In alternativa cambiare SUPABASE_BUCKET nelle variabili Railway.
