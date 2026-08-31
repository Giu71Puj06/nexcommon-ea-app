"""
Calibration Table Vallen -> colonne A1-A4 del modulo ITS.

RIFERIMENTO NORMATIVO
---------------------
Procedura EA (Bozza rev. 3), Appendice D, tabella D6, campi 22-25 del
record BD:

    22  dA12 = A12(VF finale) - A12(VF iniziale)
    23  dA21 = A21(VF finale) - A21(VF iniziale)
    24  dA34 = A34(VF finale) - A34(VF iniziale)   -> 0 con una sola coppia
    25  dA43 = A43(VF finale) - A43(VF iniziale)   -> 0 con una sola coppia

dove (par. 15.1) Aij e' l'ampiezza media dei segnali EA registrati dal
sensore j (ricevente) degli eventi prodotti dal sensore i (pulsante).

Il modulo ITS riporta questi quattro valori nelle colonne A1-A4:

    A1 = dA12    A2 = dA21    A3 = dA34    A4 = dA43

ATTENZIONE: i valori A11 e A22 (auto-impulso, cioe' l'ampiezza che il
sensore pulsante registra su se' stesso) NON hanno significato fisico
interpretabile con il pulsatore elettronico (par. 15.1) e non vanno mai
usati per A1-A4.

VERIFICA SUI CASI DI RIFERIMENTO ITS
------------------------------------
    4618790003066FG  (4 canali)  ->  1, 1, 4, 3     = modulo Lab13
    6891405736109MC  (4 canali)  -> -6, -7, -1, -1  = record BD
    4699301309864MC  (2 canali)  -> -9, -9, 0, 0    = modulo Lab12 + BD
    4699292050711MC  (2 canali)  -> -1, -1, 0, 0    = modulo (gia' noto)

Le matrici ricostruite per 4618790003066FG coincidono cifra per cifra
con gli screenshot 'Calibration Table' di VisualAE forniti da ITS.
"""

import math
import re
import sqlite3
from pathlib import Path

# Coppie di sensori previste dalla procedura: (1,2) e, per i serbatoi
# strumentati con due coppie (Appendice E, capacita' > 3 m3), (3,4).
COPPIE = ((1, 2), (3, 4))

# Celle del record BD nell'ordine A1..A4.
CELLE_A = ((1, 2), (2, 1), (3, 4), (4, 3))

# Par. 19: condizioni di accettabilita' della verifica di funzionalita' finale.
DEVIAZIONE_MAX_DB = 20.0
DIFFERENZA_DEVIAZIONI_MAX_DB = 5.0

# Par. 15.3: intervallo richiesto per le ampiezze medie ricevute in VF iniziale.
AMPIEZZA_VF_MIN_DB = 80.0
AMPIEZZA_VF_MAX_DB = 90.0

# Tolleranza temporale entro cui gli hit appartengono allo stesso colpo.
FINESTRA_COLPO_S = 0.002

# Ampiezza minima per accettare un colpo registrato dal solo ricevente.
AMPIEZZA_MIN_RICEVENTE_DB = 60.0

# Firma dell'auto-impulso: il sensore pulsante registra su se' stesso un
# segnale molto corto (decine di microsecondi), mentre i riceventi vedono
# forme d'onda lunghe centinaia o migliaia di microsecondi. Serve a
# scartare i gruppi di hit che non sono colpi di pulsatore.
# Osservato sui casi di riferimento: 23, 81, 90 e 172 us per l'emittente,
# contro 850-7400 us per i riceventi.
COLPO_DURATA_MAX_US = 300.0


def arrotonda_its(valore: float) -> int:
    """
    Arrotondamento usato da ITS per le colonne A1-A4: allo 0,5 si
    arrotonda per difetto (0,7 -> 1; 2,9 -> 3; 3,7 -> 4; 0,5 -> 0;
    -9,4 -> -9). Diverso da round() di Python, che arrotonda al pari.
    """
    intero = math.floor(valore)
    return intero if (valore - intero) <= 0.5 else intero + 1


def _amp_db(amp) -> float | None:
    """view_ae_data.Amp e' gia' in microvolt (ADC applicato dalla view)."""
    if amp is None:
        return None
    a = float(amp)
    return 20 * math.log10(a) if a > 0 else None


def _finestre_pulsing(con) -> list[tuple[float, float]]:
    """Coppie (start, end) delle finestre di pulsing, in ordine temporale."""
    eventi = []
    for r in con.execute("select Time, Data from view_ae_markers order by Time"):
        testo = r["Data"] or ""
        if r["Time"] is None:
            continue
        if re.search(r"start\s*pulsing", testo, re.I):
            eventi.append((float(r["Time"]), "start"))
        elif re.search(r"end\s*pulsing", testo, re.I):
            eventi.append((float(r["Time"]), "end"))

    finestre, apertura = [], None
    for tempo, tipo in eventi:
        if tipo == "start":
            apertura = tempo
        elif tipo == "end" and apertura is not None:
            finestre.append((apertura, tempo))
            apertura = None
    return finestre


def _colpi(con, t0: float, t1: float) -> list[list[dict]]:
    """
    Raggruppa gli hit della finestra di pulsing in singoli colpi.

    Gli hit di uno stesso colpo arrivano entro pochi microsecondi l'uno
    dall'altro; il primo in ordine di arrivo e' il sensore pulsante.
    """
    hits = []
    for r in con.execute(
        "select Time, Chan, Amp, Counts, Dur from view_ae_data "
        "where Time >= ? and Time <= ? and Amp is not null order by Time",
        (t0, t1),
    ):
        db = _amp_db(r["Amp"])
        if db is None:
            continue
        hits.append({
            "t": float(r["Time"]),
            "ch": int(r["Chan"]),
            "db": db,
            "counts": float(r["Counts"] or 0),
            "dur": float(r["Dur"] or 0),
        })

    gruppi, corrente = [], []
    for hit in hits:
        se_nuovo = corrente and (
            hit["t"] - corrente[0]["t"] > FINESTRA_COLPO_S
            or hit["ch"] in {h["ch"] for h in corrente}
        )
        if se_nuovo:
            gruppi.append(corrente)
            corrente = []
        corrente.append(hit)
    if corrente:
        gruppi.append(corrente)
    return gruppi


def _matrice(con, t0: float, t1: float, canali: list[int]) -> dict:
    """
    Ricostruisce la matrice Aij (dB) di una finestra di pulsing.

    Chiave (i, j) = sensore pulsante i, sensore ricevente j.
    La diagonale (auto-impulso) viene calcolata ma non usata per A1-A4.
    """
    somme: dict[tuple[int, int], list[float]] = {}
    gruppi = _colpi(con, t0, t1)

    def e_colpo(gruppo) -> bool:
        """
        Il primo hit del gruppo (primo arrivo) deve avere la firma
        dell'auto-impulso e almeno un altro sensore deve aver ricevuto
        un segnale di ampiezza significativa.
        """
        if len(gruppo) < 2 or gruppo[0]["dur"] > COLPO_DURATA_MAX_US:
            return False
        return any(h["db"] >= AMPIEZZA_MIN_RICEVENTE_DB for h in gruppo[1:])

    colpi = [g for g in gruppi if e_colpo(g)]
    completi = [g for g in colpi if len(g) == len(canali)]

    # I gruppi incompleti (un ricevente sotto soglia) si usano solo per i
    # sensori pulsanti che non hanno prodotto nemmeno un colpo completo,
    # altrimenti sporcherebbero le medie.
    emittenti_completi = {g[0]["ch"] for g in completi}
    usabili = completi + [g for g in colpi if g[0]["ch"] not in emittenti_completi]

    for gruppo in usabili:
        emittente = gruppo[0]["ch"]
        for hit in gruppo:
            somme.setdefault((emittente, hit["ch"]), []).append(hit["db"])

    # Configurazione a 2 canali in cui l'auto-impulso resta sotto soglia:
    # ogni colpo produce un solo hit, quello del sensore ricevente.
    if not colpi and len(canali) == 2:
        a, b = canali
        for gruppo in gruppi:
            if len(gruppo) != 1:
                continue
            hit = gruppo[0]
            if hit["db"] < AMPIEZZA_MIN_RICEVENTE_DB:
                continue
            emittente = b if hit["ch"] == a else a
            somme.setdefault((emittente, hit["ch"]), []).append(hit["db"])

    return {k: round(sum(v) / len(v), 1) for k, v in somme.items()}


def _verifica_funzionalita(differenze: dict, coppie_attive: list[tuple[int, int]]) -> dict:
    """
    Par. 19 - condizioni di accettabilita' della verifica finale:
      1. |deviazione| di ciascun sensore non maggiore di 20 dB;
      2. differenza fra le deviazioni della coppia non maggiore di 5 dB.
    Il mancato rispetto comporta la classe 0 (par. 24, nota).
    """
    motivi, deviazioni = [], {}
    for i, j in coppie_attive:
        d_ij, d_ji = differenze.get((i, j)), differenze.get((j, i))
        if d_ij is None or d_ji is None:
            motivi.append(f"coppia {i}-{j}: deviazioni non calcolabili")
            continue
        deviazioni[f"A{i}{j}"] = d_ij
        deviazioni[f"A{j}{i}"] = d_ji
        for nome, valore in ((f"A{i}{j}", d_ij), (f"A{j}{i}", d_ji)):
            if abs(valore) > DEVIAZIONE_MAX_DB:
                motivi.append(
                    f"deviazione {nome} = {valore:+.1f} dB, oltre il limite di "
                    f"{DEVIAZIONE_MAX_DB:.0f} dB (par. 19, punto 1)"
                )
        scarto = abs(d_ij - d_ji)
        if scarto > DIFFERENZA_DEVIAZIONI_MAX_DB:
            motivi.append(
                f"coppia {i}-{j}: differenza fra le deviazioni {scarto:.1f} dB, "
                f"oltre il limite di {DIFFERENZA_DEVIAZIONI_MAX_DB:.0f} dB "
                f"(par. 19, punto 2)"
            )

    if not deviazioni:
        return {"esito": "non valutabile", "motivi": motivi, "deviazioni": {}}
    return {
        "esito": "accettabile" if not motivi else "non accettabile",
        "motivi": motivi,
        "deviazioni": deviazioni,
    }


def _controllo_ampiezze_iniziali(matrice: dict, coppie_attive: list[tuple[int, int]]) -> list[str]:
    """Par. 15.3: 80 dB <= A12/A21 <= 90 dB nella verifica iniziale."""
    avvisi = []
    for i, j in coppie_attive:
        for a, b in ((i, j), (j, i)):
            valore = matrice.get((a, b))
            if valore is None:
                continue
            if not (AMPIEZZA_VF_MIN_DB <= valore <= AMPIEZZA_VF_MAX_DB):
                avvisi.append(
                    f"A{a}{b} iniziale = {valore:.1f} dB, fuori dall'intervallo "
                    f"{AMPIEZZA_VF_MIN_DB:.0f}-{AMPIEZZA_VF_MAX_DB:.0f} dB (par. 15.3)"
                )
    return avvisi


def extract_calibration(pridb_path: str | Path) -> dict:
    """
    Ricostruisce la Calibration Table dalle due verifiche di funzionalita'
    e calcola A1-A4.

    Ritorna:
      {
        'disponibile': bool,
        'canali': [1,2,...], 'coppie': [(1,2), ...],
        'iniziale' / 'finale' / 'differenze': {'1-2': dB, ...},
        'A1'..'A4': interi arrotondati secondo la regola ITS,
        'A_grezzi': {'A12': -6.3, ...},
        'verifica_funzionalita': {...},
        'avvisi': [...], 'note': str,
      }
    """
    pridb_path = Path(pridb_path)
    con = sqlite3.connect(str(pridb_path))
    con.row_factory = sqlite3.Row
    try:
        finestre = _finestre_pulsing(con)
        if not finestre:
            return {
                "disponibile": False,
                "note": "nessuna finestra di pulsing nel PRIDB: "
                        "A1-A4 non ricostruibili",
            }
        if len(finestre) < 2:
            return {
                "disponibile": False,
                "note": "presente la sola verifica di funzionalita' iniziale: "
                        "A1-A4 non calcolabili",
            }

        canali = sorted(
            int(r["Chan"])
            for r in con.execute(
                "select distinct Chan from ae_data where Chan > 0 and SetType = 2"
            )
        )
        if not canali:
            canali = sorted(
                int(r["Chan"])
                for r in con.execute("select distinct Chan from ae_data where Chan > 0")
            )
        coppie_attive = [c for c in COPPIE if c[0] in canali and c[1] in canali]

        iniziale = _matrice(con, *finestre[0], canali)
        finale = _matrice(con, *finestre[-1], canali)
        differenze = {
            k: round(finale[k] - iniziale[k], 1)
            for k in iniziale
            if k in finale
        }

        grezzi, arrotondati = {}, {}
        for indice, (i, j) in enumerate(CELLE_A, start=1):
            nome = f"A{i}{j}"
            coppia_prevista = (i, j) in COPPIE or (j, i) in COPPIE
            attiva = any({i, j} == set(c) for c in coppie_attive)
            valore = differenze.get((i, j))
            if valore is not None:
                grezzi[nome] = valore
                arrotondati[f"A{indice}"] = arrotonda_its(valore)
            elif coppia_prevista and not attiva:
                # Appendice D: con una sola coppia di sensori si scrive 0.
                grezzi[nome] = None
                arrotondati[f"A{indice}"] = 0
            else:
                grezzi[nome] = None
                arrotondati[f"A{indice}"] = None

        def etichetta(mat):
            return {f"{i}-{j}": v for (i, j), v in sorted(mat.items())}

        risultato = {
            "disponibile": True,
            "canali": canali,
            "coppie": coppie_attive,
            "iniziale": etichetta(iniziale),
            "finale": etichetta(finale),
            "differenze": etichetta(differenze),
            "matrice_iniziale": iniziale,
            "matrice_finale": finale,
            "matrice_differenze": differenze,
            "A_grezzi": grezzi,
            "verifica_funzionalita": _verifica_funzionalita(differenze, coppie_attive),
            "avvisi": _controllo_ampiezze_iniziali(iniziale, coppie_attive),
            "note": "A1=dA12, A2=dA21, A3=dA34, A4=dA43 "
                    "(Appendice D tab. D6, campi 22-25). "
                    "Con una sola coppia di sensori A3 e A4 valgono 0.",
        }
        risultato.update(arrotondati)

        mancanti = [k for k in ("A1", "A2", "A3", "A4") if risultato.get(k) is None]
        if mancanti:
            risultato["note"] += (
                f" Non ricostruiti: {', '.join(mancanti)} - verificare i colpi "
                f"di pulsatore nelle finestre di funzionalita'."
            )
        return risultato
    finally:
        con.close()
