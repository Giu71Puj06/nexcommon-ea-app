"""
Individuazione delle colonne del Modulo consegna prove EA.

Il modulo NON ha un layout stabile: i tre laboratori usano tre
disposizioni diverse per gli stessi campi.

    Lab13 (.xls)              A1-A4 su P:Q:R:S
    Lab12 (.xls, template)    A1-A4 su R:S:T:U
    Lab5  (.xlsm automatico)  A1-A4 su T:U:V:W
                              (inserisce Esito Verifica e due Contr Gen
                               dopo la colonna Y Max)

Scrivere a lettere fisse significa, prima o poi, scrivere nella colonna
sbagliata. Qui le colonne vengono individuate dal testo delle
intestazioni (righe 1 e 2 del foglio), con ripiego sul layout Lab12 se
un'intestazione non viene riconosciuta.
"""

import re

# Per ogni campo logico, le espressioni che possono comparire come
# intestazione, in ordine di priorita'. Il confronto e' su testo
# normalizzato (minuscolo, spazi compattati, accenti irrilevanti).
INTESTAZIONI = {
    "id": (r"^id$",),
    "lab": (r"^lab\.?$",),
    "data": (r"^data\b",),
    "matricola": (r"n\W*matricola", r"^matricola"),
    "localita": (r"^localit", r"^comune"),
    "provincia": (r"^prov\.?$", r"^provincia"),
    "cliente": (r"^cliente", r"^committente"),
    "numero_com": (r"^com\.?$", r"^n\W*$"),
    "ora_inizio": (r"inizio prova",),
    "naff": (r"naff", r"^t$"),
    "pressione_inizio": (r"inizio press",),
    "pressione_fine": (r"fine press",),
    "y_max": (r"^y\s*max", r"gamma"),
    "esito": (r"esito",),
    "note": (r"^note$",),
    "riserva": (r"serbatoio di riserva", r"in sostituzione"),
    "lotto": (r"n\W*lotto",),
    "a1": (r"^a1$",),
    "a2": (r"^a2$",),
    "a3": (r"^a3$",),
    "a4": (r"^a4$",),
}

# Layout Lab12, usato come ripiego campo per campo.
LAYOUT_LAB12 = {
    "id": 1, "lab": 2, "data": 3, "matricola": 4, "localita": 5,
    "provincia": 6, "cliente": 7, "numero_com": 8, "ora_inizio": 9,
    "naff": 10, "pressione_inizio": 11, "pressione_fine": 12, "y_max": 13,
    "esito": 14, "note": 15, "riserva": 16, "lotto": 17,
    "a1": 18, "a2": 19, "a3": 20, "a4": 21,
}

RIGHE_INTESTAZIONE = (1, 2, 3)
COLONNE_MASSIME = 40


def _normalizza(valore) -> str:
    testo = re.sub(r"\s+", " ", str(valore or "")).strip().lower()
    for accentata, semplice in (("à", "a"), ("è", "e"), ("é", "e"),
                                ("ì", "i"), ("ò", "o"), ("ù", "u")):
        testo = testo.replace(accentata, semplice)
    return testo


def mappa_colonne(ws) -> tuple[dict, list[str]]:
    """
    Ritorna (mappa, campi_da_ripiego).

    mappa: {campo_logico: indice_colonna_1based}
    campi_da_ripiego: campi per i quali non e' stata trovata
    un'intestazione e si e' usato il layout Lab12.
    """
    testi: dict[int, list[str]] = {}
    for riga in RIGHE_INTESTAZIONE:
        for col in range(1, COLONNE_MASSIME + 1):
            valore = _normalizza(ws.cell(row=riga, column=col).value)
            if valore:
                testi.setdefault(col, []).append(valore)

    mappa: dict[str, int | None] = {}
    occupate: set[int] = set()

    # Passo 1: assegna tutto cio' che si riconosce dalle intestazioni.
    # Va completato prima dei ripieghi, altrimenti un ripiego assegnato
    # presto occuperebbe una colonna che un campo successivo avrebbe
    # riconosciuto dal proprio titolo, sfasando tutta la mappa.
    for campo, pattern_list in INTESTAZIONI.items():
        trovata = None
        for pattern in pattern_list:
            for col, valori in sorted(testi.items()):
                if col in occupate:
                    continue
                if any(re.search(pattern, v) for v in valori):
                    trovata = col
                    break
            if trovata:
                break
        if trovata:
            mappa[campo] = trovata
            occupate.add(trovata)

    # Passo 2: per i campi rimasti, ripiego sul layout Lab12, ma solo se
    # quella colonna e' libera. Scrivere nella colonna di un altro campo
    # e' peggio che non scrivere affatto.
    ripiego = []
    for campo in INTESTAZIONI:
        if campo in mappa:
            continue
        candidata = LAYOUT_LAB12[campo]
        if candidata in occupate:
            mappa[campo] = None
        else:
            mappa[campo] = candidata
            occupate.add(candidata)
        ripiego.append(campo)

    return mappa, ripiego


def prima_riga_dati(ws, mappa: dict) -> int:
    """
    Prima riga sotto le intestazioni. Il modulo ha l'ultima intestazione
    sulla riga 2 (o 3 nei fogli che spezzano i titoli su due livelli).
    """
    colonna = mappa.get("matricola", 4)
    for riga in range(2, 8):
        sopra = ws.cell(row=riga, column=colonna).value
        if sopra and _normalizza(sopra).startswith(("serb", "n matricola",
                                                    "matricola")):
            return riga + 1
    return 3
