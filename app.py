import base64
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from nexcommon_ea.vallen_extractor import resolve_vallen_input, extract_from_pridb
from nexcommon_ea.excel_writer import create_excel_from_summary
from nexcommon_ea.supabase_io import enabled as supabase_enabled
from nexcommon_ea import package_reader as pkg


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


@st.cache_data(show_spinner=False)
def _photo_preview(path_str: str, max_side: int = 1400) -> bytes:
    """
    Legge una foto dal pacchetto e la ridimensiona per la visualizzazione.
    Le foto da smartphone sono spesso 3000-4000 px: ridurle evita di
    appesantire la pagina. Corregge anche l'orientamento EXIF.
    """
    from io import BytesIO
    from PIL import Image, ImageOps

    img = Image.open(path_str)
    img = ImageOps.exif_transpose(img)  # raddrizza le foto ruotate dal telefono
    img.thumbnail((max_side, max_side))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


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
                # Foto contenute nel pacchetto Vallen (dentro lo ZIP).
                photos = [str(p) for p in pkg.collect_photos(workdir)]

                # Foto caricata manualmente: la conserviamo e la mostriamo anche.
                if photo_file:
                    tmp_photo = Path(tempfile.mkdtemp(prefix="nexcommon_photo_")) / photo_file.name
                    tmp_photo.write_bytes(photo_file.getbuffer())
                    data["summary"]["foto_targa_pozzetto"] = str(tmp_photo)
                    if str(tmp_photo) not in photos:
                        photos.append(str(tmp_photo))

                # Inventario formati + metadati log + sintesi forme d'onda.
                inventory = pkg.inventory_package(workdir)
                acq_meta = {}
                log_files = [p for p in inventory["log"] if "(2)" not in p.name] or inventory["log"]
                if log_files:
                    acq_meta = pkg.parse_acq_log(pkg.read_log_text(log_files[0]))
                tradb_info = pkg.tradb_summary(inventory["tradb"][0]) if inventory["tradb"] else {}

                st.session_state["workdir"] = str(workdir)
                st.session_state["summary"] = data["summary"]
                st.session_state["phases"] = data["phases"]
                st.session_state["photos"] = photos
                st.session_state["inventory"] = {k: [str(p) for p in v] for k, v in inventory.items()}
                st.session_state["acq_meta"] = acq_meta
                st.session_state["tradb_info"] = tradb_info
                st.session_state["tradb_path"] = str(inventory["tradb"][0]) if inventory["tradb"] else ""
                st.success(
                    f"Dati estratti. Trovate {len(photos)} foto e "
                    f"{tradb_info.get('forme_onda', 0)} forme d'onda nel pacchetto."
                )
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

# --- Formati contenuti nel pacchetto Vallen ---------------------------------
if st.session_state.get("inventory"):
    inv = st.session_state["inventory"]
    st.markdown("### Formati nel pacchetto")
    etichette = {
        "pridb": "PRIDB (dati prova)",
        "tradb": "TRADB (forme d'onda)",
        "vaex": "VAEX (configurazione)",
        "log": "Log acquisizione",
        "foto": "Foto",
        "altri": "Altri file",
    }
    righe = []
    for chiave, label in etichette.items():
        files = inv.get(chiave, [])
        if files:
            righe.append({
                "Formato": label,
                "N. file": len(files),
                "File": ", ".join(Path(f).name for f in files),
            })
    if righe:
        st.dataframe(pd.DataFrame(righe), use_container_width=True, hide_index=True)

# --- Foto della prova -------------------------------------------------------
if st.session_state.get("photos"):
    photos = st.session_state["photos"]
    st.markdown("### Foto della prova")
    st.caption("Immagini estratte dal pacchetto Vallen (targa, pozzetto, strumentazione).")
    cols = st.columns(2)
    for i, photo_path in enumerate(photos):
        if not Path(photo_path).exists():
            continue
        with cols[i % 2]:
            try:
                st.image(
                    _photo_preview(photo_path),
                    caption=Path(photo_path).name,
                    use_container_width=True,
                )
            except Exception as exc:
                st.warning(f"Impossibile aprire {Path(photo_path).name}: {exc}")
            with open(photo_path, "rb") as fh:
                st.download_button(
                    "Scarica originale",
                    data=fh.read(),
                    file_name=Path(photo_path).name,
                    mime="image/jpeg",
                    key=f"dl_photo_{i}",
                    use_container_width=True,
                )

# --- Log di acquisizione ----------------------------------------------------
if st.session_state.get("acq_meta"):
    meta = st.session_state["acq_meta"]
    with st.expander("Log di acquisizione (dettagli strumento)"):
        etichette_log = {
            "software": "Software Vallen",
            "creato": "Creato il",
            "sistema": "Sistema operativo",
            "locale": "Locale sistema/utente",
            "unita_amsy6": "Unita AMSY-6",
            "schede": "Schede / canali",
            "canali_totali": "Canali totali",
            "fine_acquisizione": "Fine acquisizione",
            "dimensione_dati_ae": "Dimensione dati AE",
            "dimensione_dati_tr": "Dimensione dati TR",
        }
        righe_log = [
            {"Campo": etichette_log.get(k, k), "Valore": v}
            for k, v in meta.items()
        ]
        st.dataframe(pd.DataFrame(righe_log), use_container_width=True, hide_index=True)

# --- Forme d'onda (TRADB) ---------------------------------------------------
if st.session_state.get("tradb_info") and st.session_state.get("tradb_path"):
    info = st.session_state["tradb_info"]
    with st.expander(
        f"Forme d'onda transienti: {info.get('forme_onda', 0)} disponibili "
        f"({info.get('sample_rate_mhz', '?')} MHz, canali {info.get('canali')})"
    ):
        waveforms = pkg.list_waveforms(st.session_state["tradb_path"], limit=40)
        if waveforms:
            def _label(w):
                return (
                    f"TRAI {w['trai']} - ch{w['canale']} - "
                    f"{w['campioni']} campioni"
                )
            scelta = st.selectbox(
                "Seleziona una forma d'onda",
                options=waveforms,
                format_func=_label,
            )
            wf = pkg.load_waveform(st.session_state["tradb_path"], scelta["trai"])
            if wf:
                chart_df = pd.DataFrame({"mV": wf["mv"]}, index=wf["tempo_ms"])
                chart_df.index.name = "Tempo (ms)"
                st.line_chart(chart_df, use_container_width=True)
                m = wf["meta"]
                st.caption(
                    f"TRAI {m['trai']} - canale {m['canale']} - "
                    f"{m['sample_rate_mhz']} MHz - picco {m['picco_mv']} mV"
                )
        else:
            st.info("Nessuna forma d'onda leggibile nel TRADB.")

if "excel_path" in st.session_state:
    path = Path(st.session_state["excel_path"])
    st.download_button(
        "Scarica modulo ITS compilato",
        data=path.read_bytes(),
        file_name=path.name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
