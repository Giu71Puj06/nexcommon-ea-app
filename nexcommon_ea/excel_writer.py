from pathlib import Path
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
    if summary.get("data_prova"):
        ws.cell(row=row, column=3).value = summary["data_prova"]
    if summary.get("matricola"):
        ws.cell(row=row, column=4).value = summary["matricola"]
    if summary.get("provincia"):
        ws.cell(row=row, column=6).value = summary["provincia"]
    if summary.get("ora_inizio_pressurizzazione"):
        ws.cell(row=row, column=9).value = summary["ora_inizio_pressurizzazione"].replace(":", ".")
    ws.cell(row=row, column=11).value = _to_excel_num(summary.get("pressione_inizio_bar"))
    ws.cell(row=row, column=12).value = _to_excel_num(summary.get("pressione_fine_bar"))
    if summary.get("gamma_max") is not None:
        ws.cell(row=row, column=13).value = _to_excel_num(summary.get("gamma_max"))
    if summary.get("classe"):
        ws.cell(row=row, column=14).value = "IDONEO" if str(summary.get("classe")) == "1" else "NON IDONEO"
    elif summary.get("gamma_max") is not None:
        ws.cell(row=row, column=14).value = "DA VERIFICARE"
    else:
        ws.cell(row=row, column=14).value = "Y MAX DA BD/API"
    if summary.get("lotto"):
        ws.cell(row=row, column=17).value = summary["lotto"]

    note = []
    if summary.get("gradiente_bar_min") is not None:
        note.append(f"grad. {summary['gradiente_bar_min']:.3f} bar/min")
    if summary.get("hits_fondo_finale") is not None:
        note.append(f"FF hits {summary['hits_fondo_finale']}")
    if summary.get("rms_fondo_finale_uv") is not None:
        note.append(f"RMS FF {summary['rms_fondo_finale_uv']:.2f} uV")
    if summary.get("gamma_max") is None:
        note.append("Gamma non presente nel PRIDB: caricare BD.txt/listato o API Vallen")
    ws.cell(row=row, column=15).value = " | ".join(note)

    # Foglio tecnico con tutti i dati estratti, per audit e debugging.
    if "Dati Vallen" in wb.sheetnames:
        del wb["Dati Vallen"]
    audit = wb.create_sheet("Dati Vallen")
    audit.append(["Campo", "Valore"])
    for key, value in summary.items():
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
