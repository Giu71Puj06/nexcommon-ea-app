"""
Lettura dei formati contenuti nel pacchetto Vallen.

Il PRIDB e il VAEX sono gia gestiti da vallen_extractor. Questo modulo
si occupa di tutti gli ALTRI file che arrivano dentro lo ZIP Vallen e
che prima venivano ignorati:

- foto .jpg/.png/.jpeg  -> targa, pozzetto, strumentazione (da mostrare)
- .acq.log              -> log di acquisizione con metadati strumento
- .tradb                -> forme d'onda dei transienti (SQLite)

Tutte le funzioni sono difensive: se un file manca o e corrotto
restituiscono strutture vuote invece di sollevare eccezioni, cosi la
UI resta utilizzabile anche con pacchetti incompleti.
"""

import re
import sqlite3
import struct
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"}


def collect_photos(root: Path) -> list[Path]:
    """Ritorna tutte le immagini contenute nel pacchetto, ordinate per nome."""
    root = Path(root)
    if not root.exists():
        return []
    photos = [
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]
    return sorted(photos, key=lambda p: p.name.lower())


def inventory_package(root: Path) -> dict:
    """
    Classifica i file del pacchetto per formato.
    Ritorna un dizionario {categoria: [Path, ...]}.
    """
    root = Path(root)
    inv = {
        "pridb": [],
        "tradb": [],
        "vaex": [],
        "log": [],
        "foto": [],
        "altri": [],
    }
    if not root.exists():
        return inv

    for p in sorted(root.rglob("*"), key=lambda x: str(x).lower()):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext == ".pridb":
            inv["pridb"].append(p)
        elif ext == ".tradb":
            inv["tradb"].append(p)
        elif ext in (".vaex", ".vaex_bak"):
            inv["vaex"].append(p)
        elif ext == ".log":
            inv["log"].append(p)
        elif ext in IMAGE_EXTS:
            inv["foto"].append(p)
        elif ext in (".lox", ".zip"):
            # indice binario / archivio interno: non utile all'utente
            continue
        else:
            inv["altri"].append(p)
    return inv


def parse_acq_log(text: str) -> dict:
    """
    Estrae i metadati utili dal log di acquisizione Vallen (.acq.log).
    Nessun campo e obbligatorio: quelli non trovati restano assenti.
    """
    out: dict = {}
    if not text:
        return out

    # Prima riga: versione software, es. "Vallen Acquisition R2017.0504.2"
    m = re.search(r"Vallen Acquisition\s+([^\r\n]+)", text)
    if m:
        out["software"] = m.group(1).strip()

    m = re.search(r"Created:\s*([^\r\n]+)", text)
    if m:
        out["creato"] = m.group(1).strip()

    m = re.search(r"OS:\s*([^\r\n]+)", text)
    if m:
        out["sistema"] = m.group(1).strip()

    m = re.search(r"System/User locale:\s*([^\r\n]+)", text)
    if m:
        out["locale"] = m.group(1).strip()

    m = re.search(r"AMSY-6 Units\(total\)\s*:\s*(\d+)", text)
    if m:
        out["unita_amsy6"] = m.group(1)

    # Schede/canali: righe "Board: 01.01; Chans:  1 [HP-Hi], 2 [HP-Hi]; ..."
    boards = re.findall(r"Board:\s*([\d.]+);\s*Chans:\s*([^;]+);", text)
    if boards:
        out["schede"] = "; ".join(f"{b} ({c.strip()})" for b, c in boards)

    m = re.search(r"boards detected:\s*\d+\s*\(=(\d+)\s*channels\)", text)
    if m:
        out["canali_totali"] = m.group(1)

    m = re.search(r"Acquisition stopped at\s*([^\r\n]+)", text)
    if m:
        out["fine_acquisizione"] = m.group(1).strip()

    m = re.search(r"Total AE data size:\s*([^\r\n]+)", text)
    if m:
        out["dimensione_dati_ae"] = m.group(1).strip()

    m = re.search(r"Total TR data size:\s*([^\r\n]+)", text)
    if m:
        out["dimensione_dati_tr"] = m.group(1).strip()

    return out


def read_log_text(path: Path) -> str:
    """Legge un .log Vallen gestendo la codifica Windows (latin-1)."""
    raw = Path(path).read_bytes()
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="ignore")


def tradb_summary(tradb_path: Path) -> dict:
    """
    Sintesi del database dei transienti (.tradb): quante forme d'onda,
    frequenza di campionamento, canali. Ritorna {} in caso di errore.
    """
    tradb_path = Path(tradb_path)
    if not tradb_path.exists():
        return {}
    try:
        con = sqlite3.connect(str(tradb_path))
        con.row_factory = sqlite3.Row
        n = con.execute("select count(*) c from tr_data").fetchone()["c"]
        rates = [r[0] for r in con.execute(
            "select distinct SampleRate from tr_data where SampleRate is not null")]
        chans = sorted(
            {r[0] for r in con.execute(
                "select distinct Chan from tr_data where Chan is not null")}
        )
        con.close()
        sr = max(rates) if rates else None
        return {
            "forme_onda": n,
            "sample_rate_hz": sr,
            "sample_rate_mhz": round(sr / 1e6, 3) if sr else None,
            "canali": chans,
        }
    except Exception:
        return {}


def list_waveforms(tradb_path: Path, limit: int = 40) -> list[dict]:
    """Elenco delle forme d'onda disponibili (per la scelta nella UI)."""
    tradb_path = Path(tradb_path)
    if not tradb_path.exists():
        return []
    try:
        con = sqlite3.connect(str(tradb_path))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "select TRAI, Chan, Time, Samples, SampleRate "
            "from tr_data where Samples > 0 "
            "order by Samples desc limit ?",
            (limit,),
        ).fetchall()
        con.close()
        return [
            {
                "trai": r["TRAI"],
                "canale": r["Chan"],
                "tempo_s": round(float(r["Time"]), 3) if r["Time"] is not None else None,
                "campioni": r["Samples"],
                "sample_rate_hz": r["SampleRate"],
            }
            for r in rows
        ]
    except Exception:
        return []


def load_waveform(tradb_path: Path, trai: int) -> dict:
    """
    Decodifica una singola forma d'onda in millivolt.
    I campioni sono int16 little-endian moltiplicati per TR_mV.
    Ritorna {tempo_ms: [...], mv: [...], meta: {...}} oppure {}.
    """
    tradb_path = Path(tradb_path)
    if not tradb_path.exists():
        return {}
    try:
        con = sqlite3.connect(str(tradb_path))
        con.row_factory = sqlite3.Row
        row = con.execute(
            "select TRAI, Chan, SampleRate, Samples, TR_mV, Data "
            "from view_tr_data where TRAI = ?",
            (trai,),
        ).fetchone()
        con.close()
        if row is None or row["Data"] is None:
            return {}

        raw = row["Data"]
        mult = float(row["TR_mV"]) if row["TR_mV"] is not None else 1.0
        n = len(raw) // 2
        samples = struct.unpack(f"<{n}h", raw[: n * 2])
        mv = [v * mult for v in samples]

        sr = float(row["SampleRate"]) if row["SampleRate"] else None
        tempo_ms = [i / sr * 1000.0 for i in range(n)] if sr else list(range(n))
        peak = max((abs(v) for v in mv), default=0.0)

        return {
            "tempo_ms": tempo_ms,
            "mv": mv,
            "meta": {
                "trai": row["TRAI"],
                "canale": row["Chan"],
                "campioni": row["Samples"],
                "sample_rate_mhz": round(sr / 1e6, 3) if sr else None,
                "picco_mv": round(peak, 3),
            },
        }
    except Exception:
        return {}
