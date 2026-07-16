from pathlib import Path
from datetime import datetime, date

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

TEMPLATE = Path(__file__).resolve().parents[1] / "data" / "template_modulo_its.xlsx"


def _to_excel_num(value):
    if value is None or value == "":
        return ""
    try:
        return round(float(value), 3)
    except Exception:
        return value


def _to_excel_date(value):
    """
    Converte la data prova in una vera data Excel.
    La cella verra poi formattata come GG/MM/AAAA.
    Accetta:
    - datetime/date Python
    - stringhe ISO tipo 2024-06-03, 2024-06-03T10:20:30
    - stringhe italiane tipo 03/06/2024
    - stringhe con ora tipo 03/06/2024 10:20:30
    """
    if value is None or value == "":
        return ""

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return ""

    # Rimuove timezone ISO e separatore T, se presenti.
    normalized = text.replace("Z", "").replace("T", " ")

    # Prova formati frequenti.
    formats = [
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(normalized[:26], fmt).date()
        except Exception:
            pass

    # Ultimo tentativo per ISO non standard accettato da Python.
    try:
        return datetime.fromisoformat(normalized).date()
    except Exception:
        return text


def _find_or_next_row(ws, matricola: str) -> int:
    matricola = str(matricola or "").strip()
    candidate_rows = list(range(3, 23)) + list(range(34, 54))

    if matricola:
        for row in candidate_rows:
            value = ws.cell(row=row, column=4).value
            if str(value).strip() == matricola:
                return row

    for row in candidate_rows:
        if not ws.cell(row=row, column=4).value:
            return row

    return candidate_rows[-1]


def create_excel_from_summary(summary: dict, output_path: str | Path, template_path: str | Path | None = None) -> Path:
    template = Path(template_path) if template_path else TEMPLATE
    wb = load_workbook(template)
    ws = wb["MODULO CONSEGNA"] if "MODULO CONSEGNA" in wb.sheetnames else wb.active
    row = _find_or_next_row(ws, summary.get("matricola", ""))

    # Colonne del modulo ITS osservate nel file Lab12.
    ws.cell(row=row, column=2).value = 12

    # Data prova: scritta come vera data Excel e visualizzata in formato GG/MM/AAAA.
    if summary.get("data_prova"):
        data_excel = _to_excel_date(summary.get("data_prova"))
        ws.cell(row=row, column=3).value = data_excel
        if isinstance(data_excel, date):
            ws.cell(row=row, column=3).number_format = "DD/MM/YYYY"

    if summary.get("matricola"):
        ws.cell(row=row, column=4).value = summary["matricola"]

    # Località (colonna E) e Provincia (colonna F): dal master, per matricola.
    if summary.get("localita"):
        ws.cell(row=row, column=5).value = summary["localita"]

    if summary.get("provincia"):
        ws.cell(row=row, column=6).value = summary["provincia"]

    # Cliente / gasista (colonna G): dal master (proprietario).
    if summary.get("cliente"):
        ws.cell(row=row, column=7).value = summary["cliente"]

    if summary.get("ora_inizio_pressurizzazione"):
        ws.cell(row=row, column=9).value = str(summary["ora_inizio_pressurizzazione"]).replace(":", ".")

    ws.cell(row=row, column=11).value = _to_excel_num(summary.get("pressione_inizio_bar"))
    ws.cell(row=row, column=12).value = _to_excel_num(summary.get("pressione_fine_bar"))

    gamma = summary.get("gamma_max")
    if gamma is not None:
        ws.cell(row=row, column=13).value = _to_excel_num(gamma)

    # Esito (colonna N). La classificazione INAIL definitiva dipende da piu
    # controlli; qui restiamo prudenti e non dichiariamo IDONEO in automatico
    # senza la classe fornita dall'operatore.
    if summary.get("classe"):
        ws.cell(row=row, column=14).value = "IDONEO" if str(summary.get("classe")) == "1" else "NON IDONEO"
    elif gamma is not None:
        # Indicazione preliminare rispetto al limite di accettabilita (gamma lim
        # = 0,95 GPOL/CC; 0,87 REAS). Da confermare con i controlli completi.
        ws.cell(row=row, column=14).value = (
            "DA VERIFICARE (γ>lim)" if gamma > 0.87 else "DA VERIFICARE (γ≤lim)"
        )
    else:
        ws.cell(row=row, column=14).value = "Y MAX DA BD/API"

    # In sostituzione di (colonna P): matricola sostituita, dal master.
    if summary.get("in_sostituzione_di"):
        ws.cell(row=row, column=16).value = summary["in_sostituzione_di"]

    if summary.get("lotto"):
        ws.cell(row=row, column=17).value = summary["lotto"]

    # A1-A4 (colonne R/S/T/U): variazioni della Calibration Table Vallen
    # (verifica di funzionalita, confronto tra i canali C1 e C2).
    for a_key, col in (("a1", 18), ("a2", 19), ("a3", 20), ("a4", 21)):
        if summary.get(a_key) is not None:
            ws.cell(row=row, column=col).value = summary[a_key]

    note = []

    if summary.get("gradiente_bar_min") is not None:
        note.append(f"grad. {summary['gradiente_bar_min']:.3f} bar/min")

    if summary.get("hits_fondo_finale") is not None:
        note.append(f"FF hits {summary['hits_fondo_finale']}")

    if summary.get("rms_fondo_finale_uv") is not None:
        note.append(f"RMS FF {summary['rms_fondo_finale_uv']:.2f} uV")

    # Traccia la provenienza delle pressioni quando non arrivano dai marker.
    fonte_p = summary.get("fonte_pressione")
    if fonte_p and "IP1" not in str(fonte_p):
        note.append(f"pressioni da {fonte_p}")

    if gamma is not None and summary.get("gamma_source"):
        note.append(f"γmax da {summary['gamma_source']}")
    elif gamma is None:
        note.append("Gamma non presente nel PRIDB: caricare listato/BD Vallen o inserire manualmente")

    # Stato anagrafica: segnala se la matricola non e stata trovata nel master.
    stato = summary.get("anagrafica_stato")
    if stato and "non trovata" in str(stato):
        note.append("matricola non in anagrafica: Prov./Località/Cliente da inserire")

    # A1-A4 (colonne R/S/T/U): dalla Calibration Table (verifica funzionalità).
    if summary.get("a1") is not None:
        note.append("A1-A4 da Calibration Table (Δ funzionalità, da verificare)")
    else:
        note.append("A1-A4 (R/S/T/U): dati di pulsing non disponibili")

    ws.cell(row=row, column=15).value = " | ".join(note)

    # Foglio tecnico con tutti i dati estratti, per audit e debugging.
    if "Dati Vallen" in wb.sheetnames:
        del wb["Dati Vallen"]

    audit = wb.create_sheet("Dati Vallen")
    audit.append(["Campo", "Valore"])

    for key, value in summary.items():
        if key == "data_prova":
            parsed_date = _to_excel_date(value)
            audit.append([key, parsed_date])
            if isinstance(parsed_date, date):
                audit.cell(row=audit.max_row, column=2).number_format = "DD/MM/YYYY"
        else:
            audit.append([key, value])

    header_fill = PatternFill("solid", fgColor="D9EAF7")
    thin = Side(style="thin", color="B7B7B7")

    for cell in audit[1]:
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.border = Border(bottom=thin)

    audit.column_dimensions["A"].width = 35
    audit.column_dimensions["B"].width = 45

    output_path = Path(output_path)
    wb.save(output_path)
    return output_path
