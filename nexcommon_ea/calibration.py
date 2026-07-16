"""
Calibration Table Vallen -> colonne A1-A4 del modulo ITS.

La verifica di funzionalita EA usa l'auto-calibrazione (pulsing): ogni
sensore emette un impulso e l'altro lo riceve. Vallen esegue questa
calibrazione all'inizio (funzionalita iniziale) e alla fine
(funzionalita finale) della prova.

Nel PRIDB, gli impulsi sono registrati come hit dentro le finestre
'Start Pulsing' / 'End Pulsing'. Per ogni finestra e per ogni canale si
distinguono:
- ampiezza di AUTO-IMPULSO (self): il sensore che pulsa (valore alto);
- ampiezza RICEVUTA (recv): il segnale che arriva dall'altro sensore.

Le colonne A1-A4 del modulo sono le variazioni (finale - iniziale) di
queste ampiezze, arrotondate. Il valore e stato validato sul serbatoio
50711 (modulo: A1=-1, A2=-1, A3=0).

NOTA: la tabella grezza completa viene restituita perche l'operatore
possa confrontarla con la pagina 'Calibration Table' di VisualAE.
"""

import math
import re
import sqlite3
from pathlib import Path


def _amp_db(amp) -> float | None:
    if amp is None:
        return None
    a = float(amp)
    return 20 * math.log10(a) if a > 0 else None


def _pulsing_windows(con) -> list[tuple[float, float]]:
    """Coppie (start, end) delle finestre di pulsing, in ordine temporale."""
    starts, ends = [], []
    for r in con.execute("select Time, Data from view_ae_markers order by Time"):
        txt = r["Data"] or ""
        t = float(r["Time"])
        if re.search(r"start\s*pulsing", txt, re.I):
            starts.append(t)
        elif re.search(r"end\s*pulsing", txt, re.I):
            ends.append(t)
    windows = []
    for s in starts:
        later = [e for e in ends if e >= s]
        if later:
            windows.append((s, min(later)))
    return windows


def _window_table(con, t0: float, t1: float) -> dict:
    """
    Per una finestra di pulsing ritorna, per canale, l'ampiezza media di
    auto-impulso (self) e ricevuta (recv), separandole per canale con una
    soglia dinamica a meta scala.
    """
    per_ch: dict[int, list[float]] = {}
    for r in con.execute(
        "select Chan, Amp from view_ae_data "
        "where Time >= ? and Time <= ? and Amp is not null",
        (t0, t1),
    ):
        db = _amp_db(r["Amp"])
        if db is None or db < 50:  # scarta rumore di soglia
            continue
        per_ch.setdefault(r["Chan"], []).append(db)

    table = {}
    for ch, amps in per_ch.items():
        if not amps:
            continue
        lo, hi = min(amps), max(amps)
        mid = (lo + hi) / 2
        # Se il range e stretto (<10 dB) c'e un solo tipo di misura.
        if hi - lo < 10:
            self_vals, recv_vals = amps, []
        else:
            self_vals = [a for a in amps if a >= mid]
            recv_vals = [a for a in amps if a < mid]
        table[ch] = {
            "self": round(sum(self_vals) / len(self_vals), 2) if self_vals else None,
            "recv": round(sum(recv_vals) / len(recv_vals), 2) if recv_vals else None,
        }
    return table


def extract_calibration(pridb_path: str | Path) -> dict:
    """
    Ricostruisce la Calibration Table e calcola A1-A4.

    Ritorna:
      {
        'iniziale': {ch: {'self':dB,'recv':dB}},
        'finale':   {ch: {'self':dB,'recv':dB}},
        'A1'..'A4': variazione finale-iniziale arrotondata,
        'canali': [...],
        'note': '...'
      }
    Se i dati di pulsing non ci sono, ritorna {'disponibile': False}.
    """
    pridb_path = Path(pridb_path)
    con = sqlite3.connect(str(pridb_path))
    con.row_factory = sqlite3.Row
    try:
        windows = _pulsing_windows(con)
        if not windows:
            return {"disponibile": False, "note": "nessuna finestra di pulsing nel PRIDB"}

        ini = _window_table(con, *windows[0])
        fin = _window_table(con, *windows[-1]) if len(windows) > 1 else {}

        channels = sorted(set(ini) | set(fin))

        def delta(ch, kind):
            a = ini.get(ch, {}).get(kind)
            b = fin.get(ch, {}).get(kind)
            if a is None or b is None:
                return None
            return round(b - a)

        # A1/A2 = variazione auto-impulso ch1/ch2; A3/A4 = variazione ricevuta.
        result = {
            "disponibile": True,
            "iniziale": ini,
            "finale": fin,
            "canali": channels,
            "A1": delta(1, "self"),
            "A2": delta(2, "self"),
            "A3": delta(1, "recv"),
            "A4": delta(2, "recv"),
            "note": "A1/A2 = Δ auto-impulso ch1/ch2; A3/A4 = Δ ricevuta ch1/ch2 (finale-iniziale)",
        }
        if not fin:
            result["note"] = "solo calibrazione iniziale presente: A1-A4 non calcolabili"
        return result
    finally:
        con.close()
