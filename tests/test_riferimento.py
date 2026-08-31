"""
Casi di riferimento ITS: verificano che l'app produca esattamente i valori
scritti a mano dagli operatori.

Uso:
    python tests/test_riferimento.py /percorso/cartella_con_i_pacchetti

La cartella viene esplorata in ricorsiva alla ricerca dei file .pridb; per
ogni pacchetto riconosciuto fra quelli attesi si confrontano A1-A4 e, se
presente il record BD, pressioni e gamma.

I quattro casi sono quelli consegnati da ITS a fine agosto 2026:
il pacchetto 50711 gia' presente nel repository e i tre pacchetti
"PUNTO 1" (due a 4 canali da 5000 L e uno a 2 canali da 3000 L).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexcommon_ea.calibration import extract_calibration  # noqa: E402
from nexcommon_ea.bd_record import parse_bd_record  # noqa: E402

ATTESI = {
    # serbatoio: (A1, A2, A3, A4, canali, fonte del valore atteso)
    "4699292050711MC": ((-1, -1, 0, 0), 2, "modulo Lab12"),
    "4618790003066FG": ((1, 1, 4, 3), 4, "modulo Lab13 + screenshot VisualAE"),
    "6891405736109MC": ((-6, -7, -1, -1), 4, "record BD"),
    "4699301309864MC": ((-9, -9, 0, 0), 2, "modulo Lab12 + record BD"),
}

# Il record BD di questo serbatoio riporta A3=3 mentre la Calibration Table
# (e il modulo compilato a mano) danno 4. Discrepanza aperta con ITS.
BD_DIVERGENTI = {"4618790003066FG": (1, 1, 3, 3)}


def esegui(radice: Path) -> int:
    pridb = sorted(radice.rglob("*.pridb"))
    if not pridb:
        print(f"Nessun file .pridb sotto {radice}")
        return 1

    falliti, eseguiti = 0, 0
    for percorso in pridb:
        nome = percorso.stem.replace("_EA", "")
        if nome not in ATTESI:
            continue
        eseguiti += 1
        atteso, canali_attesi, fonte = ATTESI[nome]

        cal = extract_calibration(percorso)
        ottenuto = tuple(cal.get(k) for k in ("A1", "A2", "A3", "A4"))
        ok_a = ottenuto == atteso
        ok_ch = len(cal.get("canali", [])) == canali_attesi
        falliti += 0 if (ok_a and ok_ch) else 1

        print(f"[{'OK ' if ok_a and ok_ch else 'KO '}] {nome}  "
              f"{len(cal.get('canali', []))} canali")
        print(f"       A1-A4 {ottenuto}  atteso {atteso}  ({fonte})")
        print(f"       grezzi {cal.get('A_grezzi')}")
        print(f"       verifica funzionalita': "
              f"{cal.get('verifica_funzionalita', {}).get('esito')}")

        bd = next(percorso.parent.glob("*_BD.txt"), None)
        if bd:
            record = parse_bd_record(bd.read_text(encoding="utf-8",
                                                  errors="ignore"))
            a_bd = tuple(record.get(k) for k in ("a1", "a2", "a3", "a4"))
            atteso_bd = BD_DIVERGENTI.get(nome, atteso)
            stato = "OK " if a_bd == atteso_bd else "KO "
            if a_bd != atteso_bd:
                falliti += 1
            print(f"[{stato}] {nome}  record BD  A {a_bd}  "
                  f"p {record.get('pressione_inizio_bar')}/"
                  f"{record.get('pressione_fine_bar')} bar  "
                  f"gamma {record.get('gamma_max')}")
            if nome in BD_DIVERGENTI:
                print("       NOTA: il BD diverge dalla Calibration Table, "
                      "discrepanza nota da chiarire con ITS")

    if not eseguiti:
        print("Nessuno dei pacchetti di riferimento trovato sotto "
              f"{radice}. Attesi: {', '.join(ATTESI)}")
        return 1

    print(f"\n{eseguiti} casi eseguiti, {falliti} verifiche fallite")
    return 1 if falliti else 0


if __name__ == "__main__":
    radice = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("Input")
    raise SystemExit(esegui(radice))
