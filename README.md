# Nexcommon EA - Vallen to ITS

Applicazione Streamlit per ridurre la trascrizione manuale dei dati Vallen nei moduli ITS.

## Funzioni

1. Carica ZIP Vallen o `.pridb`.
2. Estrae dati prova: pressioni, orari, marker, RMS, hit, fondo finale.
3. Salva la pratica su Supabase, se configurato.
4. Genera il modulo Excel ITS compilato.

## Avvio locale

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Variabili Railway

Impostare in Railway > Service > Variables:

```text
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_BUCKET=ea-prove
```

Il file `.env` non va caricato su GitHub.

## Supabase

Eseguire `sql/supabase_schema.sql` nel SQL Editor di Supabase.
Creare un bucket Storage privato chiamato `ea-prove`.

## Deploy Railway

1. Creare repository GitHub e caricare questi file.
2. In Railway: New Project > Deploy from GitHub repo.
3. Aggiungere le variabili Supabase.
4. Railway avvia Streamlit con il comando in `railway.json`.

## Nota su Gamma Max

Il valore `Y Max / Gamma Max` non è sempre salvato nel `.pridb` standard. Quando disponibile, caricare anche `BD.txt` o listato Vallen. In mancanza, l'app consente un inserimento manuale temporaneo.
