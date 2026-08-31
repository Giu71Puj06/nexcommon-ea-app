# Modifiche — validazione riscontro ITS (agosto 2026)

Base normativa: **Bozza Procedura EA rev. 3**, gia' presente in `Input/`.
Casi di riferimento: pacchetto 50711 del repository + i tre pacchetti
"PUNTO 1" consegnati da ITS.

## Correzioni

### 1. `nexcommon_ea/calibration.py` — riscritto

La regola A1-A4 era sbagliata. Calcolava:

    A1 = Δ auto-impulso ch1      A3 = Δ ampiezza ricevuta ch1
    A2 = Δ auto-impulso ch2      A4 = Δ ampiezza ricevuta ch2

L'Appendice D, tabella D6, campi 22-25, definisce invece:

    A1 = ΔA12    A2 = ΔA21    A3 = ΔA34    A4 = ΔA43

Gli auto-impulsi A11 e A22, che il codice usava per A1 e A2, "non hanno
significato fisicamente interpretabile" con il pulsatore elettronico
(par. 15.1).

Esito sui casi di riferimento, prima e dopo:

| Serbatoio | Prima | Dopo | Atteso |
|---|---|---|---|
| 4699292050711MC | −1 · −1 · 0 · 0 | −1 · −1 · 0 · 0 | −1 · −1 · 0 · 0 |
| 4618790003066FG | −1 · −2 · 0 · −10 | **1 · 1 · 4 · 3** | 1 · 1 · 4 · 3 |
| 6891405736109MC | *nessun valore* | **−6 · −7 · −1 · −1** | −6 · −7 · −1 · −1 |
| 4699301309864MC | 3 · 3 · — · — | **−9 · −9 · 0 · 0** | −9 · −9 · 0 · 0 |

Altro nello stesso file:

- ricostruzione della matrice Aij completa, 2 e 4 canali (prima gestiva
  solo self/recv per canale, con separazione a meta' scala);
- riconoscimento dei colpi di pulsatore per durata dell'auto-impulso;
- arrotondamento ITS (0,5 per difetto) al posto di `round()`, che
  arrotonda al pari;
- A3 e A4 posti a 0 con una sola coppia di sensori, come prescrive
  l'Appendice D;
- verifica del par. 19 (deviazioni ≤ 20 dB, scarto fra deviazioni ≤ 5 dB).

Le matrici ricostruite per 4618790003066FG coincidono cifra per cifra con
gli screenshot VisualAE forniti da ITS.

### 2. `nexcommon_ea/bd_record.py` — nuovo

`parse_bd_gamma` richiedeva almeno 28 campi: i record BD di ITS ne hanno
26, quindi non scattava mai. Gli indici erano comunque disallineati
(leggeva γmax come pressione di inizio e la data come γmax).

Il nuovo parser riconosce entrambi i formati per ancore (lotto, codice di
interruzione, matricola del Responsabile) invece che per posizione, ed
estrae anche anagrafica, classe e le quattro ΔA.

### 3. `nexcommon_ea/valutazione.py` — nuovo

Applica i par. 16-24: γstop, γlim, soglie N75/N85/NCORR, diagnosi del
fondo finale, condizioni di pressurizzazione, classificazione 0/1/2.
Produce una **proposta motivata**, non un verdetto: controlli preliminari,
controlli integrativi e trafilamenti non sono nei dati Vallen.

### 4. `nexcommon_ea/layout_modulo.py` — nuovo

Le colonne del modulo vengono individuate dal testo delle intestazioni.
I tre laboratori usano tre layout diversi (A1-A4 su `P:Q:R:S`, `R:S:T:U`,
`T:U:V:W`): scrivere a lettere fisse prima o poi sbaglia colonna.

### 5. `nexcommon_ea/vallen_extractor.py`

- `infer_from_filename`: matricola a 6 caratteri esatti (era `{5,7}`),
  anno espanso a 4 cifre, distinzione fra provincia di immatricolazione
  (nome file) e di installazione (colonna Prov. del modulo);
- `phase_stats` non filtra piu' `canale in (1, 2)`: escludeva i canali 3
  e 4 dei serbatoi oltre 5000 L;
- RMS del rumore di fondo letto dai set di stato (SetType 3), che portano
  l'RMS continuo, invece che dagli hit;
- il record BD viene usato come riscontro sulle A1-A4 e la divergenza
  viene segnalata nelle note.

### 6. `nexcommon_ea/excel_writer.py`

- scrittura sulle colonne individuate dalle intestazioni;
- la cella "Inizio prova" non viene piu' compilata con l'inizio della
  pressurizzazione: nel modulo e' l'ora di arrivo in sito, che non e' nei
  dati Vallen. L'orario misurato va nelle note;
- l'esito e' `DA CONFERMARE: ...` finche' l'operatore non indica la classe;
- il lotto viene scritto senza il prefisso `L2R`, come nei moduli.

### 7. `data/template_modulo_its.xlsx` — ripulito

Conteneva 31 record reali di altri serbatoi e 38 righe di anomalie con
annotazioni sui clienti, che finivano in ogni modulo generato e sono
raggiungibili dall'istanza pubblica su Railway. Righe dati svuotate,
intestazioni, formule e blocchi firma mantenuti.

### 8. `tests/test_riferimento.py` — nuovo

    python tests/test_riferimento.py /percorso/dei/pacchetti

Confronta A1-A4, pressioni e γmax con i valori scritti a mano dagli
operatori sui quattro casi di riferimento.

## Da chiarire con ITS

1. **PUNTO 3 non consegnato**: mancano gli screenshot "Gamma Max" e
   "Listato Generale" per le due configurazioni.
2. **4618790003066FG**: il record BD riporta A3 = 3, la Calibration Table
   e il modulo compilato a mano danno 4. Quale valore e' andato a INAIL?
3. **Naff / Ncorr**: tre notazioni diverse nei tre moduli (`8`, `0/3`,
   `0/18/0/4`). Il campo non e' ancora automatizzato.
4. **"CAT −1,xx"** nelle note del Modulo Automatico: cos'e' e come entra
   nel giudizio.
5. **Master `_elab.xlsx`**: il link SharePoint richiede autorizzazione.
