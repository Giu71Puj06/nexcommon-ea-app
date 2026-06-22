import math
import re
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

PHASE_CODES = ["IC1", "FC1", "IN1", "FN1", "IP1", "FP1", "IR1", "FR1"]


def resolve_vallen_input(uploaded_file) -> tuple[Path, Path | None, Path]:
    workdir = Path(tempfile.mkdtemp(prefix="nexcommon_vallen_"))
    source = workdir / uploaded_file.name
    source.write_bytes(uploaded_file.getbuffer())
    if source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as zf:
            zf.extractall(workdir)
        pridb_files = list(workdir.rglob("*.pridb"))
        if not pridb_files:
            raise ValueError("Nel file ZIP non ho trovato nessun file .pridb Vallen.")
        pridb = pridb_files[0]
        vaex_files = list(workdir.rglob("*.vaex"))
        vaex = vaex_files[0] if vaex_files else None
        return pridb, vaex, workdir
    if source.suffix.lower() == ".pridb":
        vaex = source.with_suffix(".vaex") if source.with_suffix(".vaex").exists() else None
        return source, vaex, workdir
    raise ValueError("Caricare un file .zip Vallen oppure un file .pridb.")


def get_pressure_scaling(vaex_path: Path | None) -> tuple[float, float]:
    offset, factor = 1000.0, 0.00625
    if vaex_path and vaex_path.exists():
        try:
            root = ET.parse(vaex_path).getroot()
            for node in root.iter():
                name = (node.attrib.get("Name", "") or "").lower()
                long_name = (node.attrib.get("LongName", "") or "").lower()
                if node.tag.endswith("Input") and (name in ("press", "pressure") or long_name == "pressure"):
                    offset = float(node.attrib.get("Offset", offset))
                    factor = float(node.attrib.get("Factor", factor))
                    break
        except Exception:
            pass
    return offset, factor


def infer_from_filename(name: str) -> dict:
    stem = Path(name).stem.upper().replace("_EA", "")
    # Pattern observed: 4699292050711MC_EA -> lotto 46992, anno 92, matricola 50711, provincia MC
    m = re.search(r"(\d{5})(\d{2})(\d{5,7})([A-Z]{2})$", stem)
    if m:
        return {
            "lotto": m.group(1),
            "anno": m.group(2),
            "matricola": str(int(m.group(3))),
            "provincia": m.group(4),
        }
    m2 = re.search(r"(\d{4,7})([A-Z]{2})$", stem)
    return {"matricola": str(int(m2.group(1))) if m2 else "", "provincia": m2.group(2) if m2 else ""}


def parse_bd_gamma(text: str) -> dict:
    """Parse optional INAIL BD record. Field 20 is gamma max in Appendix D."""
    out = {}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines:
        parts = ln.split(";")
        if len(parts) >= 28:
            out["pressione_inizio_bar"] = _num(parts[16])
            out["pressione_fine_bar"] = _num(parts[17])
            out["interruzione_precauzionale"] = parts[18]
            out["gamma_max"] = _num(parts[19])
            out["fondo_finale_esito"] = parts[20]
            out["classe"] = parts[25]
            return out
    return out


def _num(value):
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return None


def extract_from_pridb(pridb_path: Path, vaex_path: Path | None = None, bd_text: str | None = None) -> dict:
    offset, factor = get_pressure_scaling(vaex_path)
    con = sqlite3.connect(str(pridb_path))
    con.row_factory = sqlite3.Row

    acq_start = None
    for row in con.execute("select Data from ae_markers order by SetID"):
        data = row["Data"] or ""
        match = re.search(r"(20\d\d-\d\d-\d\d \d\d:\d\d:\d\d)", data)
        if match:
            acq_start = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
            break

    markers = {}
    marker_rows = []
    for row in con.execute("select SetID, Number, Data, SetType, Time from view_ae_markers order by SetID"):
        txt = row["Data"] or ""
        code = None
        match = re.search(r"\b(" + "|".join(PHASE_CODES) + r")\b", txt)
        if match:
            code = match.group(1)
            markers[code] = float(row["Time"])
        marker_rows.append({"codice": code or "", "testo": txt, "tempo_s": float(row["Time"])})

    pressure_points = []
    for row in con.execute("select Time, PA0 from view_ae_data where PA0 is not null order by Time"):
        pressure = (float(row["PA0"]) - offset) * factor
        pressure_points.append((float(row["Time"]), pressure))

    def nearest_pressure(t: float):
        if not pressure_points:
            return None
        return min(pressure_points, key=lambda item: abs(item[0] - t))[1]

    hits = []
    for row in con.execute("select Time, Chan, Amp, Dur, Eny, RMS, Counts, TRAI from view_ae_data where Amp is not null order by Time"):
        amp_uv = float(row["Amp"]) if row["Amp"] is not None else None
        amp_db = 20 * math.log10(amp_uv) if amp_uv and amp_uv > 0 else None
        hits.append({
            "tempo_s": float(row["Time"]),
            "canale": row["Chan"],
            "ampiezza_db": amp_db,
            "durata_us": row["Dur"],
            "energia_eu": row["Eny"],
            "rms_uv": row["RMS"],
            "counts": row["Counts"],
            "trai": row["TRAI"],
            "pressione_bar": nearest_pressure(float(row["Time"])),
        })

    def phase_stats(start_code: str, end_code: str) -> dict:
        if start_code not in markers or end_code not in markers:
            return {}
        t0, t1 = markers[start_code], markers[end_code]
        subset = [h for h in hits if t0 <= h["tempo_s"] <= t1 and h["canale"] in (1, 2)]
        pp = [p for p in pressure_points if t0 <= p[0] <= t1]
        return {
            "inizio_s": t0,
            "fine_s": t1,
            "durata_s": t1 - t0,
            "ora_inizio": (acq_start + timedelta(seconds=t0)).strftime("%H:%M:%S") if acq_start else "",
            "ora_fine": (acq_start + timedelta(seconds=t1)).strftime("%H:%M:%S") if acq_start else "",
            "pressione_inizio_bar": nearest_pressure(t0),
            "pressione_fine_bar": nearest_pressure(t1),
            "pressione_max_bar": max([p[1] for p in pp], default=None),
            "hits": len(subset),
            "ampiezza_max_db": max([h["ampiezza_db"] for h in subset if h["ampiezza_db"] is not None], default=None),
            "rms_max_uv": max([h["rms_uv"] for h in subset if h["rms_uv"] is not None], default=None),
            "eventi_ge_75db": sum(1 for h in subset if h["ampiezza_db"] is not None and h["ampiezza_db"] >= 75),
            "eventi_ge_85db": sum(1 for h in subset if h["ampiezza_db"] is not None and h["ampiezza_db"] >= 85),
        }

    phases = {
        "funzionalita_iniziale": phase_stats("IC1", "FC1"),
        "fondo_iniziale": phase_stats("IN1", "FN1"),
        "pressurizzazione": phase_stats("IP1", "FP1"),
        "fondo_finale": phase_stats("IR1", "FR1"),
    }
    con.close()

    press = phases["pressurizzazione"]
    delta_p = None
    grad = None
    if press.get("pressione_inizio_bar") is not None and press.get("pressione_fine_bar") is not None:
        delta_p = press["pressione_fine_bar"] - press["pressione_inizio_bar"]
        if press.get("durata_s"):
            grad = delta_p / (press["durata_s"] / 60)

    inferred = infer_from_filename(pridb_path.name)
    summary = {
        "file_vallen": pridb_path.name,
        "data_prova": acq_start.strftime("%d/%m/%Y") if acq_start else "",
        "ora_acquisizione": acq_start.strftime("%H:%M") if acq_start else "",
        "matricola": inferred.get("matricola", ""),
        "provincia": inferred.get("provincia", ""),
        "lotto": inferred.get("lotto", ""),
        "pressione_inizio_bar": press.get("pressione_inizio_bar"),
        "pressione_fine_bar": press.get("pressione_fine_bar"),
        "pressione_max_bar": press.get("pressione_max_bar"),
        "delta_p_bar": delta_p,
        "gradiente_bar_min": grad,
        "ora_inizio_pressurizzazione": press.get("ora_inizio", "")[:5],
        "ora_fine_pressurizzazione": press.get("ora_fine", "")[:5],
        "hits_pressurizzazione": press.get("hits"),
        "rms_fondo_iniziale_uv": phases["fondo_iniziale"].get("rms_max_uv"),
        "hits_fondo_finale": phases["fondo_finale"].get("hits"),
        "rms_fondo_finale_uv": phases["fondo_finale"].get("rms_max_uv"),
        "eventi_fondo_finale_ge_75db": phases["fondo_finale"].get("eventi_ge_75db"),
        "eventi_fondo_finale_ge_85db": phases["fondo_finale"].get("eventi_ge_85db"),
        "gamma_max": None,
        "interruzione_precauzionale": "N",
        "fondo_finale_esito": "",
        "classe": "",
    }
    if bd_text:
        summary.update({k: v for k, v in parse_bd_gamma(bd_text).items() if v is not None and v != ""})

    return {"summary": summary, "phases": phases, "markers": marker_rows}
