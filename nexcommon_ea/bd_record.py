"""
Lettura del record BD (Riepilogo Banca Dati EA dell'Inail).

Il record e' una riga di campi separati da ';'. La procedura EA definisce
28 campi nell'Appendice D, tabella D6, ma i file prodotti oggi da ITS ne
hanno 26 e in ordine diverso: manca il numero di fabbrica, mancano gli
esiti dei controlli preliminari e integrativi, e le quattro differenze di
ampiezza stanno dopo la data anziche' prima della classe.

    Appendice D  ... ;Pini;Pfin;INT;gmax;FF;dA12;dA21;dA34;dA43;classe;matr;data;
    ITS          ... ;Pini;Pfin;INT;gmax;classe;matr;data;dA12;dA21;dA34;dA43;T;T

Per questo il parser non usa posizioni fisse ma tre ancore riconoscibili:

    - il lotto omogeneo          L2R46187 / L3R00167
    - il codice di interruzione  N, GS, A85, A75, ACORR
    - la matricola Responsabile  GPL200707EA081

Le pressioni sono i due campi numerici che precedono il codice di
interruzione, gmax e' quello che lo segue. Entrambi i formati vengono
letti correttamente.
"""

import re

INTERRUZIONE_CODICI = ("N", "GS", "A85", "A75", "ACORR")
RIVESTIMENTI = ("REAS", "GPOL", "CC")

RE_LOTTO = re.compile(r"^L\dR\w+$", re.I)
RE_RESPONSABILE = re.compile(r"^GPL\w*EA\w+$", re.I)
RE_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def _num(valore):
    if valore is None or str(valore).strip() == "":
        return None
    try:
        return float(str(valore).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def _intero(valore):
    n = _num(valore)
    return int(round(n)) if n is not None else None


def _e_intero(valore) -> bool:
    return bool(re.fullmatch(r"[+-]?\d+", str(valore).strip()))


def _indice(campi, predicato):
    for i, c in enumerate(campi):
        if predicato(c):
            return i
    return None


def parse_bd_record(testo: str) -> dict:
    """
    Legge la prima riga valida di un file BD e ne restituisce i campi.

    Ritorna {} se nessuna riga e' riconoscibile come record BD.
    """
    for riga in (l.strip() for l in (testo or "").splitlines()):
        if ";" not in riga:
            continue
        campi = [c.strip() for c in riga.split(";")]
        risultato = _leggi_record(campi)
        if risultato:
            risultato["bd_campi_totali"] = len(campi)
            return risultato
    return {}


def _leggi_record(campi: list[str]) -> dict:
    i_lotto = _indice(campi, lambda c: RE_LOTTO.match(c))
    if i_lotto is None or i_lotto < 6:
        return {}

    out: dict = {
        "anno_immatricolazione": campi[0] if campi else "",
        "matricola": campi[1].lstrip("0") if len(campi) > 1 else "",
        "provincia_immatricolazione": campi[2] if len(campi) > 2 else "",
        "proprietario": campi[i_lotto - 6],
        "indirizzo": campi[i_lotto - 5],
        "civico": campi[i_lotto - 4],
        "cap": campi[i_lotto - 3],
        "comune": campi[i_lotto - 2],
        "provincia_installazione": campi[i_lotto - 1],
        "lotto": campi[i_lotto],
    }
    # Il numero di fabbrica c'e' solo nel formato dell'Appendice D.
    if i_lotto >= 10:
        out["numero_fabbrica"] = campi[3]

    if i_lotto + 1 < len(campi):
        out["organismo"] = campi[i_lotto + 1]
    for c in campi[i_lotto + 1: i_lotto + 4]:
        if c.upper() in RIVESTIMENTI:
            out["rivestimento"] = c.upper()
            break

    # --- Ancora 2: codice di interruzione precauzionale --------------------
    i_int = _indice(
        campi,
        lambda c: c.upper() in INTERRUZIONE_CODICI,
    )
    # Deve essere preceduto dalle due pressioni.
    while i_int is not None and not (
        i_int >= 2
        and _num(campi[i_int - 1]) is not None
        and _num(campi[i_int - 2]) is not None
    ):
        successivo = _indice(
            campi[i_int + 1:], lambda c: c.upper() in INTERRUZIONE_CODICI
        )
        i_int = None if successivo is None else i_int + 1 + successivo

    if i_int is not None:
        out["pressione_inizio_bar"] = _num(campi[i_int - 2])
        out["pressione_fine_bar"] = _num(campi[i_int - 1])
        out["interruzione_precauzionale"] = campi[i_int].upper()
        if i_int + 1 < len(campi):
            out["gamma_max"] = _num(campi[i_int + 1])
            out["gamma_source"] = "record BD INAIL"

    # --- Ancora 3: matricola del Responsabile ------------------------------
    i_resp = _indice(campi, lambda c: RE_RESPONSABILE.match(c))
    if i_resp is not None:
        out["matricola_responsabile"] = campi[i_resp]
        if i_resp >= 1 and _e_intero(campi[i_resp - 1]):
            out["classe"] = campi[i_resp - 1]

    i_data = _indice(campi, lambda c: RE_DATA.match(c))
    if i_data is not None:
        out["data_prova"] = campi[i_data]

    # Le quattro differenze di ampiezza: dopo la data (formato ITS) oppure
    # subito prima della classe (formato Appendice D).
    delte = None
    if i_data is not None:
        coda = campi[i_data + 1: i_data + 5]
        if len(coda) == 4 and all(_e_intero(c) for c in coda):
            delte = coda
    if delte is None and i_resp is not None and i_resp >= 5:
        blocco = campi[i_resp - 5: i_resp - 1]
        if len(blocco) == 4 and all(_e_intero(c) for c in blocco):
            delte = blocco
            if i_resp >= 6:
                out["fondo_finale_esito"] = campi[i_resp - 6]

    if delte:
        for etichetta, valore in zip(("a1", "a2", "a3", "a4"), delte):
            out[etichetta] = _intero(valore)
        out["a_source"] = "record BD INAIL"

    return out


# ---------------------------------------------------------------------------
# Compatibilita' con il codice esistente
# ---------------------------------------------------------------------------

def parse_bd_gamma(testo: str) -> dict:
    """Manteneuta per compatibilita': ritorna i soli campi di prova."""
    record = parse_bd_record(testo)
    if not record:
        return {}
    chiavi = (
        "pressione_inizio_bar", "pressione_fine_bar",
        "interruzione_precauzionale", "gamma_max", "gamma_source",
        "fondo_finale_esito", "classe", "rivestimento",
        "a1", "a2", "a3", "a4", "a_source",
        "proprietario", "comune", "provincia_installazione",
        "indirizzo", "lotto", "matricola_responsabile",
    )
    return {k: record[k] for k in chiavi if k in record}
