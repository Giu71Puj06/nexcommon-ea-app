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

## Colonne A1-A4 — Calibration Table

Le colonne A1-A4 sono le **differenze di ampiezza fra la verifica di
funzionalita' finale e quella iniziale**, definite dall'Appendice D
(tabella D6, campi 22-25) della Procedura EA:

| Colonna | Campo BD | Definizione |
|---|---|---|
| A1 | 22 | ΔA12 = A12 finale − A12 iniziale |
| A2 | 23 | ΔA21 |
| A3 | 24 | ΔA34 — **0** con una sola coppia di sensori |
| A4 | 25 | ΔA43 — **0** con una sola coppia di sensori |

dove Aij (par. 15.1) e' l'ampiezza media registrata dal sensore *j*
(ricevente) degli impulsi prodotti dal sensore *i* (pulsante).

I valori di auto-impulso A11 e A22 **non vanno usati**: con il pulsatore
elettronico non hanno significato fisico interpretabile (par. 15.1).

L'app ricostruisce l'intera matrice Aij dai colpi di pulsatore registrati
nel PRIDB fra le label `Start Pulsing` e `End Pulsing`, per 2 o 4 canali,
e applica l'arrotondamento usato da ITS: **allo 0,5 si arrotonda per
difetto** (0,7 → 1; 2,9 → 3; 3,7 → 4; 0,5 → 0).

Sono verificate anche le condizioni del par. 19: deviazione di ciascun
sensore entro 20 dB e scarto fra le deviazioni della coppia entro 5 dB.
Il mancato rispetto comporta la classe 0.

### Casi di riferimento

    python tests/test_riferimento.py /percorso/dei/pacchetti

| Serbatoio | Canali | A1-A4 | Riscontro |
|---|---|---|---|
| 4699292050711MC | 2 | −1 · −1 · 0 · 0 | modulo Lab12 |
| 4618790003066FG | 4 | 1 · 1 · 4 · 3 | modulo Lab13 + screenshot VisualAE |
| 6891405736109MC | 4 | −6 · −7 · −1 · −1 | record BD |
| 4699301309864MC | 2 | −9 · −9 · 0 · 0 | modulo Lab12 + record BD |

Le matrici ricostruite per 4618790003066FG coincidono cifra per cifra con
gli screenshot della pagina Calibration Table forniti da ITS.

**Discrepanza aperta**: per 4618790003066FG il record BD riporta
1 · 1 · 3 · 3 mentre la Calibration Table e il modulo compilato a mano
danno 1 · 1 · 4 · 3. L'app segnala la divergenza nelle note.

## Record BD INAIL

Il parser (`nexcommon_ea/bd_record.py`) legge due formati:

- **Appendice D**, 28 campi, ordine `... ;gmax;FF;ΔA12;ΔA21;ΔA34;ΔA43;classe;matricola;data`;
- **formato ITS**, 26 campi, senza numero di fabbrica e senza gli esiti dei
  controlli preliminari/integrativi, con le ΔA **dopo** la data.

Non usa posizioni fisse ma tre ancore: il lotto (`L2R46187`), il codice di
interruzione precauzionale (`N`, `GS`, `A85`, `A75`, `ACORR`) e la
matricola del Responsabile (`GPL200707EA081`). Le pressioni sono i due
campi numerici che precedono il codice di interruzione, γmax quello che lo
segue.

Dal record BD l'app ricava anche localita', provincia di installazione,
proprietario e tipologia di rivestimento quando il master non e' stato
caricato.

## Valutazione della prova e proposta di classe

`nexcommon_ea/valutazione.py` applica i paragrafi 16-24 della Procedura EA:

| Riferimento | Controllo |
|---|---|
| par. 16 | RMS del rumore di fondo iniziale ≤ 10 µV |
| par. 17 | gradiente ≤ 0,2 (+0,05) bar/min, p_max 14,0 (+0,5) bar, Δp ≥ 4,5 bar |
| par. 18 tab. 6 | diagnosi dell'attivita' di fondo finale |
| par. 19 | accettabilita' della verifica di funzionalita' finale |
| par. 22 tab. 7 | γstop (1 GPOL/CC, 0,95 REAS) e limiti N75 / N85 / NCORR |
| par. 23 tab. 8 | γlim (0,95 GPOL/CC, 0,87 REAS) |
| par. 24 tab. 9 | classificazione 0 / 1 / 2 |

**L'esito non viene mai dichiarato in autonomia.** L'app produce una
proposta motivata: l'esito dei controlli preliminari e integrativi e
l'assenza di trafilamenti non sono ricavabili dai dati Vallen, e i
conteggi N75 / N85 / NCORR sono fatti sugli hit registrati nella finestra
di fondo finale, non sugli eventi localizzati. Nella colonna Esito viene
scritto `DA CONFERMARE: ...` finche' l'operatore non indica la classe.

## Layout del modulo

Il Modulo consegna prove EA **non ha colonne fisse**: i tre laboratori
usano disposizioni diverse (A1-A4 su `P:Q:R:S`, `R:S:T:U`, `T:U:V:W`).
`nexcommon_ea/layout_modulo.py` individua le colonne dal testo delle
intestazioni e ripiega sul layout Lab12 solo per i campi non riconosciuti,
segnalandolo nelle note.

## Provincia: attenzione a quale

- il nome del pacchetto Vallen porta la provincia di **immatricolazione**
  (la targa): `4618790003066FG` → `FG`;
- la colonna Prov. del modulo vuole quella di **installazione**: per lo
  stesso serbatoio `CN` (Barolo).

Sono due campi distinti e non vanno incrociati. L'app li tiene separati
(`provincia_immatricolazione` e `provincia`).

## Nome del pacchetto Vallen (15 caratteri)

    4699301309864MC_EA
    |___||_||_____||_|
    lotto an matr. pr

- 5 caratteri: lotto omogeneo, nei master con prefisso `L2R`;
- 2 caratteri: anno di immatricolazione (01 → 2001, 90 → 1990);
- 6 caratteri: matricola, con zeri di riempimento (nei master spesso senza);
- 2 lettere: provincia di immatricolazione.

Suffisso `_EA` per tutti i file, `_BD` per il record Banca Dati.

## Nota su Gamma Max (Y Max)

γmax non e' salvato nei file grezzi del pacchetto: il `.vaex` configura il
processore ICSE/ISRE ma il risultato numerico resta in VisualAE. Va inoltre
letto **solo fra le label IP e FP**: caricando l'intera prova si ottiene un
valore non reale.

Per i serbatoi oltre 5000 L (due coppie di sensori) γmax e' calcolato su
entrambe le coppie e vale il maggiore, ma in quella configurazione non
compare nel Listato Generale: va letto dalla pagina "Gamma Max".

Le tre fonti, in ordine di priorita':

1. record BD INAIL;
2. listato/export VisualAE con la colonna Gamma;
3. inserimento manuale dalla barra laterale.

## Pressioni (colonne K/L)

Dal canale parametrico PA0 del PRIDB ai marker IP1 e FP1. La `view_ae_data`
applica gia' i fattori di scala, la conversione in bar usa `Offset` e
`Factor` del `.vaex`. Scarto misurato rispetto ai moduli ITS: ≤ 0,03 bar.

Se i marker mancano, le pressioni vengono ricavate dalla curva e la cosa
viene segnalata nelle note.

## Ora di inizio prova

**Non e' ricavabile dai dati Vallen.** Nel modulo e' l'ora di arrivo in
sito (spegnimento e posizionamento del furgone), che precede di parecchi
minuti il primo evento registrato. La cella resta da compilare a mano;
l'orario di inizio pressurizzazione finisce nelle note.

## Dati nel repository

Il template `data/template_modulo_its.xlsx` conteneva 31 record reali di
altri serbatoi e 38 righe di anomalie con annotazioni sui clienti, che
finivano in ogni modulo generato: le righe dati sono state svuotate
mantenendo intestazioni, formule e blocchi firma.

La cartella `Input/` contiene ancora un pacchetto Vallen reale e le
procedure in PDF. Valutare se debba stare in un repository pubblico.
