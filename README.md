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

## Anagrafica master serbatoi

I dati anagrafici del serbatoio non sono nel pacchetto Vallen ma nel file
master (es. `Master_L_autogas_..._elab.xlsx`). Caricandolo nell'app, in base
alla **matricola** (colonna `N°matr`) vengono compilati automaticamente:

- **Provincia** (colonna F del modulo) da `prov. Inst`;
- **Località** (colonna E) da `loc. inst`;
- **Cliente / gasista** (colonna G) da `proprietario`;
- **Y Max / Gamma** (colonna M) dalla colonna `Y` del master, quando non
  già ricavato da listato/BD/inserimento manuale;
- **In sostituzione di** (colonna P) da `Matr. Sost.`.

Se la matricola non è presente in anagrafica, l'app lo segnala e lascia i
campi da compilare manualmente.

## Colonne A1-A4 (R/S/T/U) — Calibration Table

Le colonne A1-A4 provengono dalla **Calibration Table** della verifica di
funzionalità EA (confronto tra i canali C1 e C2). L'app le ricostruisce dai
dati di pulsing del PRIDB: per ogni canale misura l'ampiezza di auto-impulso
e quella ricevuta, all'inizio e alla fine prova, e calcola:

- **A1 / A2** = variazione (finale − iniziale) dell'auto-impulso di C1 / C2;
- **A3 / A4** = variazione (finale − iniziale) dell'ampiezza ricevuta.

I valori sono ricostruiti dai dati grezzi e vanno **verificati** rispetto
alla pagina Calibration Table di VisualAE prima della consegna (validati sul
serbatoio 50711: A1=−1, A2=−1, A3=0).

## Nota su Gamma Max (Y Max)

Il valore `Y Max / Gamma Max` è l'indicatore sintetico γmax calcolato in
tempo reale dal processore ICSE di Vallen VisualAE (definito nel file
`.vaex`, a partire da ICSE e ISRE). **Il valore calcolato non è salvato nei
file grezzi del pacchetto** (pridb/tradb/vaex/acq_setup): il vaex configura
solo il processore, ma il risultato numerico resta in VisualAE.

Per compilare la colonna Y Max del modulo ITS ci sono tre strade, in ordine
di priorità:

1. **Listato / export Vallen**: caricare il file di testo/CSV esportato da
   VisualAE contenente la colonna Gamma (o un'etichetta `GammaMax = ...`).
   L'app ne estrae automaticamente il massimo.
2. **Record BD INAIL**: se disponibile il record BD (campi separati da `;`),
   l'app legge γmax e la classe.
3. **Inserimento manuale**: dalla barra laterale, quando le altre fonti non
   sono disponibili.

Le pressioni di inizio/fine pressurizzazione (colonne K/L) provengono dal
canale PA0 ai marker IP1/FP1; se i marker non sono presenti, l'app le ricava
automaticamente dalla curva di pressione e lo segnala nelle note.
