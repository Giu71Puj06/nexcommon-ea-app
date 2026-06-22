import base64
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from nexcommon_ea.vallen_extractor import resolve_vallen_input, extract_from_pridb
from nexcommon_ea.excel_writer import create_excel_from_summary
from nexcommon_ea.supabase_io import enabled as supabase_enabled


st.set_page_config(
    page_title="Nexcommon EA - Vallen to ITS",
    page_icon="ITS",
    layout="wide",
)


def _find_logo() -> Path | None:
    candidates = [
        Path("Logo ITS.png"),
        Path("logo_its.png"),
        Path("assets/Logo ITS.png"),
        Path("assets/logo_its.png"),
        Path("static/Logo ITS.png"),
        Path("data/Logo ITS.png"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _logo_as_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


logo_path = _find_logo()
logo_html = ""
if logo_path:
    logo_html = (
        f'<img src="data:image/png;base64,{_logo_as_base64(logo_path)}" '
        'class="its-logo" alt="ITS Controlli Tecnici SpA" />'
    )
else:
    logo_html = '<div class="its-logo-fallback">ITS<br/>CONTROLLI<br/>TECNICI SpA</div>'

st.markdown(
    """
    <style>
    :root {
        --its-blue: #009ee3;
        --its-navy: #061d3b;
        --panel: #111827;
        --panel-soft: #1f2937;
        --text-soft: #c9d2df;
    }

    .stApp {
        background: linear-gradient(135deg, #07111f 0%, #0b1220 42%, #061d3b 100%);
    }

    section[data-testid="stSidebar"] {
        background: #111827;
        border-right: 1px solid rgba(255,255,255,0.08);
    }

    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] span {
        color: #f8fafc !important;
    }

    .block-container {
        padding-top: 3.2rem;
        padding-bottom: 5rem;
        max-width: 1220px;
    }

    .its-hero {
        display: flex;
        align-items: center;
        gap: 34px;
        padding: 30px 34px;
        border-radius: 22px;
        background: rgba(6, 29, 59, 0.78);
        border: 1px solid rgba(0, 158, 227, 0.28);
        box-shadow: 0 24px 70px rgba(0, 0, 0, 0.28);
        margin-bottom: 26px;
    }

    .its-logo {
        width: 255px;
        max-width: 255px;
        height: auto;
        border-radius: 2px;
        display: block;
        background: #061d3b;
    }

    .its-logo-fallback {
        width: 255px;
        padding: 18px 20px;
        background: #061d3b;
        color: #ffffff;
        font-size: 31px;
        line-height: 1.05;
        font-weight: 800;
        letter-spacing: 0.02em;
        border-left: 10px solid var(--its-blue);
    }

    .hero-title {
        margin: 0;
        color: #ffffff;
        font-size: 3.4rem;
        line-height: 1.02;
        font-weight: 850;
        letter-spacing: -0.04em;
    }

    .hero-subtitle {
        margin-top: 16px;
        color: var(--text-soft);
        font-size: 1.08rem;
        max-width: 820px;
    }

    .section-card {
        padding: 26px 28px 20px 28px;
        background: rgba(17, 24, 39, 0.88);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 20px;
        margin-top: 18px;
    }

    .section-title {
        color: #ffffff;
        font-size: 1.35rem;
        font-weight: 750;
        margin: 0 0 4px 0;
    }

    .section-help {
        color: #9ca3af;
        margin: 0 0 18px 0;
    }

    div.stButton > button[kind="primary"] {
        background: var(--its-blue) !important;
        color: #ffffff !important;
        border: 1px solid var(--its-blue) !important;
        border-radius: 12px !important;
        font-weight: 800 !important;
    }

    div.stButton > button:not([kind="primary"]) {
        border-radius: 12px !important;
        font-weight: 800 !important;
    }

    .nexcommon-footer {
        position: fixed;
        right: 22px;
        bottom: 12px;
        z-index: 999999;
        color: rgba(226, 232, 240, 0.78);
        font-size: 12px;
        background: rgba(6, 29, 59, 0.72);
        border: 1px solid rgba(0, 158, 227, 0.24);
        border-radius: 999px;
        padding: 8px 13px;
        backdrop-filter: blur(8px);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="its-hero">
        <div>{logo_html}</div>
        <div>
            <h1 class="hero-title">Nexcommon EA</h1>
            <div class="hero-subtitle">
                Estrazione automatica dati Vallen e compilazione del modulo consegna prove EA ITS.
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="nexcommon-footer">Piattaforma creata da Nexcommon Srl</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Configurazione")
    st.write("Supabase:", "attivo" if supabase_enabled() else "non configurato")
    gamma_manuale = st.number_input(
        "Y Max / Gamma Max manuale, solo se manca BD/API",
        min_value=0.0,
        max_value=5.0,
        value=0.0,
        step=0.01,
    )
    classe_manuale = st.selectbox("Classe prova", ["", "0", "1", "2"], index=0)
    st.info(
        "Gamma Max non è sempre salvato nel PRIDB. "
        "Caricare anche BD.txt/listato quando disponibile."
    )

st.markdown(
    """
    <div class="section-card">
        <p class="section-title">Caricamento dati prova</p>
        <p class="section-help">Carica lo ZIP Vallen o il PRIDB, poi genera il modulo Excel ITS.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

zip_file = st.file_uploader("Carica ZIP Vallen o PRIDB", type=["zip", "pridb"])
bd_file = st.file_uploader(
    "Opzionale: carica BD.txt o listato Vallen con Gamma Max",
    type=["txt", "csv", "log"],
)
photo_file = st.file_uploader(
    "Opzionale: foto targa/pozzetto da mantenere nella sessione",
    type=["jpg", "jpeg", "png"],
)

col1, col2 = st.columns(2)

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
                if photo_file:
                    tmp_photo = Path(tempfile.mkdtemp(prefix="nexcommon_photo_")) / photo_file.name
                    tmp_photo.write_bytes(photo_file.getbuffer())
                    data["summary"]["foto_targa_pozzetto"] = str(tmp_photo)
                st.session_state["workdir"] = str(workdir)
                st.session_state["summary"] = data["summary"]
                st.session_state["phases"] = data["phases"]
                st.success("Dati estratti correttamente.")
            except Exception as exc:
                st.exception(exc)

with col2:
    if st.button("2. Genera Excel ITS", type="primary", use_container_width=True):
        if "summary" not in st.session_state:
            st.error("Prima estrai i dati Vallen.")
        else:
            outdir = Path(tempfile.mkdtemp(prefix="nexcommon_excel_"))
            matricola = st.session_state["summary"].get("matricola", "prova")
            outpath = outdir / f"Modulo_ITS_{matricola}.xlsx"
            create_excel_from_summary(st.session_state["summary"], outpath)
            st.session_state["excel_path"] = str(outpath)
            st.success("Excel generato.")

if "summary" in st.session_state:
    st.markdown("### Dati estratti")
    df = pd.DataFrame([st.session_state["summary"]]).T.reset_index()
    df.columns = ["Campo", "Valore"]
    st.dataframe(df, use_container_width=True, hide_index=True)

if "excel_path" in st.session_state:
    path = Path(st.session_state["excel_path"])
    st.download_button(
        "Scarica modulo ITS compilato",
        data=path.read_bytes(),
        file_name=path.name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
