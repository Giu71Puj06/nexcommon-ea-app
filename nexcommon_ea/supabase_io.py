import os
from datetime import datetime
from pathlib import Path
from supabase import create_client, Client


def enabled() -> bool:
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))


def get_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def save_run(summary: dict, files: list[Path] | None = None) -> dict:
    if not enabled():
        return {"enabled": False, "message": "Supabase non configurato"}
    client = get_client()
    payload = {
        "matricola": str(summary.get("matricola", "")),
        "lotto": str(summary.get("lotto", "")),
        "data_prova": summary.get("data_prova") or None,
        "pressione_inizio_bar": summary.get("pressione_inizio_bar"),
        "pressione_fine_bar": summary.get("pressione_fine_bar"),
        "gamma_max": summary.get("gamma_max"),
        "classe": str(summary.get("classe", "")),
        "raw_summary": summary,
    }
    inserted = client.table("ea_runs").insert(payload).execute()
    run_id = inserted.data[0]["id"] if inserted.data else None
    uploaded = []
    bucket = os.getenv("SUPABASE_BUCKET", "ea-prove")
    for file_path in files or []:
        if file_path and Path(file_path).exists():
            storage_path = f"{datetime.utcnow().strftime('%Y/%m/%d')}/{run_id or 'no-id'}/{Path(file_path).name}"
            client.storage.from_(bucket).upload(storage_path, Path(file_path).read_bytes(), {"upsert": "true"})
            uploaded.append(storage_path)
    return {"enabled": True, "run_id": run_id, "uploaded": uploaded}
