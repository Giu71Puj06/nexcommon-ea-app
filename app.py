import json
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from nexcommon_ea.vallen_extractor import resolve_vallen_input, extract_from_pridb
from nexcommon_ea.excel_writer import create_excel_from_summary
from nexcommon_ea.supabase_io import save_run, enabled as supabase_enabled

st.set_page_config(page_title="Nexcommon EA - Vallen to ITS", layout="wide")

# -----------------------------------------------------------------------------
# Intestazione applicazione
# Mantiene tutte le funzionalita esistenti e aggiunge logo ITS + credit Nexcommon.
# Per funzionare su Railway, caricare il file "Logo ITS.png" nella root del repo
# oppure in una delle cartelle: data/, assets/, static/.
# -----------------------------------------------------------------------------

def find_logo_path() -> Path | None:
    candidates = [
        Path("Logo ITS.png"),
        Path("logo_its.png"),
        Path("data/Logo ITS.png"),
        Path("data/logo_its.png"),
        Path("assets/Logo ITS.png"),
        Path("assets/logo_its.png"),
        Path("static/Logo ITS.png"),
        Path("static/logo_its.png"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None

logo_path = find_logo_path()

header_col_logo, header_col_title = st.columns([1, 4])
with header_col_logo:
    if logo_path:
        st.image(str(logo_path), width=240)
    else:
        st.markdown("### ITS Controlli Tecnici SpA")

with header_col_title:
    st.title("Nexcommon EA")
    st.caption("Estrazione automatica dati Vallen e compilazione modulo consegna prove EA ITS")
    st.markdown("**Piattaforma creata da Nexcommon Srl**")

with st.sidebar:
    st.header("Configurazione")
    st.write("Supabase:", "attivo" if supabase_enabled() else "non configurato")
    gamma_manuale = st.number_input("Y Max / Gamma Max manuale, solo se manca BD/API", min_value=0.0, max_value=5.0, value=0.0, step=0.01)
    classe_manuale = st.selectbox("Classe prova", ["", "0", "1", "2"], index=0)
    st.info("Gamma Max non è sempre salvato nel PRIDB. Caricare anche BD.txt/listato quando disponibile.")
    st.markdown("---")
    st.caption("Piattaforma creata da Nexcommon Srl")

zip_file = st.file_uploader("Carica ZIP Vallen o PRIDB", type=["zip", "pridb"])
bd_file = st.file_uploader("Opzionale: carica BD.txt o listato Vallen con Gamma Max", type=["txt", "csv", "log"])
photo_file = st.file_uploader("Opzionale: foto targa/pozzetto da archiviare", type=["jpg", "jpeg", "png"])

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("1. Estrai dati Vallen", type="primary", use_container_width=True):
        if not zip_file:
            st.error("Carica prima uno ZIP Vallen o un PRIDB.")
        else:
            try:
                pridb, vaex, workdir = resolve_vallen_input(zip_file)
                bd_text = bd_file.getvalue().decode("utf-8", errors="ignore") if bd_file else None
                data = extract_from_pridb(pridb, vaex, bd_text)
                if gamma_manuale > 0 and data["summary"].get("gamma_max") is None:
                    data["summary"]["gamma_max"] = gamma_manuale
                if classe_manuale:
                    data["summary"]["classe"] = classe_manuale
                st.session_state["workdir"] = str(workdir)
                st.session_state["summary"] = data["summary"]
                st.session_state["phases"] = data["phases"]
                st.success("Dati estratti correttamente.")
            except Exception as exc:
                st.exception(exc)

with col2:
    if st.button("2. Salva pratica su Supabase", use_container_width=True):
        if "summary" not in st.session_state:
            st.error("Prima estrai i dati Vallen.")
        else:
            files = []
            if photo_file:
                tmp = Path(tempfile.mkdtemp()) / photo_file.name
                tmp.write_bytes(photo_file.getbuffer())
                files.append(tmp)
            result = save_run(st.session_state["summary"], files)
            if result.get("enabled"):
                st.success(f"Pratica salvata. ID: {result.get('run_id')}")
            else:
                st.warning(result.get("message"))

with col3:
    if st.button("3. Genera Excel ITS", type="primary", use_container_width=True):
        if "summary" not in st.session_state:
            st.error("Prima estrai i dati Vallen.")
        else:
            outdir = Path(tempfile.mkdtemp(prefix="nexcommon_excel_"))
            outpath = outdir / f"Modulo_ITS_{st.session_state['summary'].get('matricola','prova')}.xlsx"
            create_excel_from_summary(st.session_state["summary"], outpath)
            st.session_state["excel_path"] = str(outpath)
            st.success("Excel generato.")

if "summary" in st.session_state:
    st.subheader("Dati estratti")
    df = pd.DataFrame([st.session_state["summary"]]).T.reset_index()
    df.columns = ["Campo", "Valore"]
    st.dataframe(df, use_container_width=True, hide_index=True)

if "excel_path" in st.session_state:
    path = Path(st.session_state["excel_path"])
    st.download_button("Scarica modulo ITS compilato", data=path.read_bytes(), file_name=path.name, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.markdown("---")
footer_col_left, footer_col_right = st.columns([2, 1])
with footer_col_left:
    st.caption("Piattaforma creata da Nexcommon Srl")
with footer_col_right:
    if logo_path:
        st.image(str(logo_path), width=160)
