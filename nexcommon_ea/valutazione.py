"""
Valutazione della prova EA secondo la Procedura EA (Bozza rev. 3).

Riferimenti implementati:

  par. 16       rumore di fondo iniziale: RMS <= 10 uV su ogni canale
  par. 17       pressurizzazione: gradiente <= 0,2 (+0,05) bar/min,
                p_max = 14,0 (+0,5) bar, delta p >= 4,5 bar
  par. 18 t.6   diagnosi dell'attivita' di fondo finale
  par. 19       accettabilita' della verifica di funzionalita' finale
  par. 22 t.7   interruzione precauzionale (gamma_stop, N75, N85, NCORR)
  par. 23 t.8   valore limite di accettabilita' gamma_lim
  par. 24 t.9   classificazione della prova

L'ESITO NON VIENE MAI DICHIARATO IN AUTONOMIA. Questo modulo produce una
proposta motivata: alcune condizioni della tabella 9 (esito dei controlli
preliminari e integrativi, presenza di trafilamenti o perdite di GPL) non
sono contenute nei dati Vallen e restano a carico dell'operatore.
"""

# --- par. 23, tabella 8 ---
GAMMA_LIM = {"GPOL": 0.95, "CC": 0.95, "REAS": 0.87}

# --- par. 22.1 ---
GAMMA_STOP = {"GPOL": 1.00, "CC": 1.00, "REAS": 0.95}

# --- par. 22.2, tabella 7 ---
N_CORR_LIM = {"GPOL": 1500, "CC": 1500, "REAS": 1000}
N_75_LIM = {"GPOL": 30, "CC": 30, "REAS": 25}
N_85_LIM = {"GPOL": 10, "CC": 10, "REAS": 8}

# --- par. 18, tabella 6: diagnosi dell'attivita' di fondo finale ---
FONDO_FINALE = {
    "GPOL": {"gamma": 0.80, "soglia_db": 85, "n_min": 3, "n_corr": 300},
    "CC": {"gamma": 0.80, "soglia_db": 85, "n_min": 3, "n_corr": 300},
    "REAS": {"gamma": 0.70, "soglia_db": 75, "n_min": 3, "n_corr": 250},
}

# --- par. 17 ---
GRADIENTE_MAX_BAR_MIN = 0.2 + 0.05
P_MAX_BAR = 14.0
P_MAX_TOLLERANZA_BAR = 0.5
DELTA_P_MIN_BAR = 4.5

# --- par. 16 ---
RMS_FONDO_INIZIALE_MAX_UV = 10.0

CONTROLLI_NON_AUTOMATIZZABILI = (
    "esito dei controlli preliminari e integrativi (par. 10 e 11)",
    "assenza di trafilamenti o perdite di GPL",
)


def _riv(rivestimento) -> str:
    r = str(rivestimento or "").strip().upper()
    return r if r in GAMMA_LIM else "REAS"


def valuta(summary: dict, calibration: dict | None = None) -> dict:
    """
    Ritorna:
      {
        'rivestimento': 'REAS',
        'gamma_max': 0.4, 'gamma_lim': 0.87, 'gamma_stop': 0.95,
        'controlli': [{'voce','riferimento','esito','dettaglio'}, ...],
        'classe_proposta': '1' | '2' | '0' | '',
        'motivi': [...],
        'da_verificare': [...],
        'sintesi': 'testo per la colonna Note',
      }
    """
    rivestimento = _riv(summary.get("rivestimento"))
    gamma = summary.get("gamma_max")
    g_lim = GAMMA_LIM[rivestimento]
    g_stop = GAMMA_STOP[rivestimento]
    fondo = FONDO_FINALE[rivestimento]

    controlli: list[dict] = []
    motivi_classe_2: list[str] = []
    motivi_classe_0: list[str] = []

    def aggiungi(voce, riferimento, esito, dettaglio):
        controlli.append({
            "voce": voce,
            "riferimento": riferimento,
            "esito": esito,
            "dettaglio": dettaglio,
        })

    # --- par. 23: gamma_max rispetto al limite di accettabilita' ----------
    if gamma is None:
        aggiungi("Indicatore sintetico γmax", "par. 23",
                 "non valutabile",
                 "γmax non disponibile: caricare il record BD o il listato "
                 "VisualAE (Gamma Max fra IP e FP), oppure inserirlo a mano")
    else:
        entro = gamma <= g_lim
        aggiungi("Indicatore sintetico γmax", "par. 23",
                 "conforme" if entro else "non conforme",
                 f"γmax = {gamma:.2f}, limite {rivestimento} = {g_lim:.2f}")
        if not entro:
            motivi_classe_2.append(
                f"γmax {gamma:.2f} oltre il limite {g_lim:.2f} ({rivestimento})"
            )

        # --- par. 22.1: soglia di interruzione precauzionale --------------
        if gamma >= g_stop:
            aggiungi("Interruzione precauzionale (γ)", "par. 22.1",
                     "non conforme",
                     f"γmax = {gamma:.2f} ≥ γstop {g_stop:.2f}: la prova "
                     f"andava interrotta")
            motivi_classe_2.append(f"γmax ≥ γstop ({g_stop:.2f})")

    # --- par. 22.2: numero di eventi -------------------------------------
    n85 = summary.get("eventi_fondo_finale_ge_85db")
    n75 = summary.get("eventi_fondo_finale_ge_75db")
    ncorr = summary.get("hits_fondo_finale")

    superate = []
    if n85 is not None and n85 > N_85_LIM[rivestimento]:
        superate.append(f"N85 = {n85} > {N_85_LIM[rivestimento]}")
    if n75 is not None and n75 > N_75_LIM[rivestimento]:
        superate.append(f"N75 = {n75} > {N_75_LIM[rivestimento]}")
    if ncorr is not None and ncorr > N_CORR_LIM[rivestimento]:
        superate.append(f"NCORR = {ncorr} > {N_CORR_LIM[rivestimento]}")

    aggiungi("Numero di eventi", "par. 22.2, tab. 7",
             "non conforme" if superate else "conforme",
             "; ".join(superate) if superate
             else f"N85 {n85}, N75 {n75}, NCORR {ncorr} entro i limiti "
                  f"{rivestimento}")
    if superate:
        motivi_classe_2.append("superati i valori limite precauzionali: "
                               + "; ".join(superate))

    # --- par. 18, tab. 6: diagnosi dell'attivita' di fondo finale ---------
    n_aff = n85 if fondo["soglia_db"] == 85 else n75
    if gamma is not None and n_aff is not None and ncorr is not None:
        cond_a = gamma >= fondo["gamma"] and n_aff >= fondo["n_min"]
        cond_b = ncorr >= fondo["n_corr"]
        negativa = cond_a or cond_b
        aggiungi("Attività di fondo finale", "par. 18, tab. 6",
                 "negativa" if negativa else "positiva",
                 f"γmax {gamma:.2f} (soglia {fondo['gamma']:.2f}), "
                 f"N{fondo['soglia_db']} = {n_aff} (soglia {fondo['n_min']}), "
                 f"NCORR = {ncorr} (soglia {fondo['n_corr']})")
        if negativa:
            motivi_classe_2.append("diagnosi negativa dell'attività di fondo "
                                   "finale (par. 18)")
    else:
        aggiungi("Attività di fondo finale", "par. 18, tab. 6",
                 "non valutabile",
                 "servono γmax e i conteggi di eventi del fondo finale")

    # --- par. 19: verifica di funzionalita' finale ------------------------
    vf = (calibration or {}).get("verifica_funzionalita") or {}
    if vf.get("esito") == "accettabile":
        aggiungi("Verifica di funzionalità finale", "par. 19", "conforme",
                 "deviazioni entro 20 dB e scarto fra le deviazioni entro 5 dB")
    elif vf.get("esito") == "non accettabile":
        aggiungi("Verifica di funzionalità finale", "par. 19", "non conforme",
                 "; ".join(vf.get("motivi", [])))
        motivi_classe_0.append("verifica di funzionalità finale non conforme "
                               "(par. 19 → classe 0)")
    else:
        aggiungi("Verifica di funzionalità finale", "par. 19",
                 "non valutabile",
                 "dati di pulsing insufficienti per ricostruire le deviazioni")

    # --- par. 17: pressurizzazione ---------------------------------------
    grad = summary.get("gradiente_bar_min")
    p_fin = summary.get("pressione_fine_bar")
    delta_p = summary.get("delta_p_bar")
    problemi = []
    if grad is not None and grad > GRADIENTE_MAX_BAR_MIN:
        problemi.append(f"gradiente {grad:.3f} bar/min > "
                        f"{GRADIENTE_MAX_BAR_MIN:.2f}")
    if p_fin is not None and p_fin < P_MAX_BAR - P_MAX_TOLLERANZA_BAR:
        problemi.append(f"p_max {p_fin:.3f} bar sotto {P_MAX_BAR:.1f} bar")
    if delta_p is not None and delta_p < DELTA_P_MIN_BAR:
        problemi.append(f"Δp {delta_p:.3f} bar < {DELTA_P_MIN_BAR:.1f} bar")
    aggiungi("Pressurizzazione", "par. 17",
             "non conforme" if problemi else "conforme",
             "; ".join(problemi) if problemi
             else f"p {summary.get('pressione_inizio_bar')} → {p_fin} bar, "
                  f"Δp {delta_p:.3f} bar" if delta_p is not None else "")

    # --- par. 16: rumore di fondo iniziale -------------------------------
    rms = summary.get("rms_fondo_iniziale_uv")
    if rms is not None:
        aggiungi("Rumore di fondo iniziale", "par. 16",
                 "conforme" if rms <= RMS_FONDO_INIZIALE_MAX_UV
                 else "non conforme",
                 f"RMS max {rms:.2f} µV (limite "
                 f"{RMS_FONDO_INIZIALE_MAX_UV:.0f} µV)")

    # --- par. 24: proposta di classificazione ----------------------------
    if motivi_classe_0:
        classe, motivi = "0", motivi_classe_0
    elif motivi_classe_2:
        classe, motivi = "2", motivi_classe_2
    elif gamma is None:
        classe, motivi = "", ["γmax non disponibile: classe non proponibile"]
    else:
        classe = "1"
        motivi = [f"γmax {gamma:.2f} ≤ γlim {g_lim:.2f}",
                  "nessun superamento dei valori limite precauzionali",
                  "verifica di funzionalità finale conforme"
                  if vf.get("esito") == "accettabile"
                  else "verifica di funzionalità finale da confermare"]

    etichetta = {"0": "NON CLASSIFICABILE", "1": "CONFORME",
                 "2": "NON CONFORME"}.get(classe, "DA COMPLETARE")

    sintesi = f"proposta classe {classe} ({etichetta})" if classe \
        else "classe non proponibile"
    if gamma is not None:
        sintesi += f" · γmax {gamma:.2f}/{g_lim:.2f} {rivestimento}"

    return {
        "rivestimento": rivestimento,
        "gamma_max": gamma,
        "gamma_lim": g_lim,
        "gamma_stop": g_stop,
        "controlli": controlli,
        "classe_proposta": classe,
        "etichetta_classe": etichetta,
        "motivi": motivi,
        "da_verificare": list(CONTROLLI_NON_AUTOMATIZZABILI),
        "sintesi": sintesi,
        "avvertenza": "Proposta automatica da par. 16-24 della Procedura EA. "
                      "La classificazione finale resta di competenza "
                      "dell'Organismo Competente Abilitato: gli esiti dei "
                      "controlli preliminari e integrativi e l'assenza di "
                      "trafilamenti non sono ricavabili dai dati Vallen. "
                      "N75/N85/NCORR sono conteggiati sugli hit registrati "
                      "nella finestra di fondo finale, non sugli eventi "
                      "localizzati: verificarli in VisualAE prima di "
                      "chiudere la classificazione.",
    }
