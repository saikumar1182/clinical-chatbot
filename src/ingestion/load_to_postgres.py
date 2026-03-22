from sqlalchemy import text
import json
from src.db.connection import engine


def load_trials_batch(trials: list[dict], batch_id: str) -> int:
    rows = [
        {
            "nct_id": t["protocolSection"]["identificationModule"]["nctId"],
            "raw_json": json.dumps(t),
            "batch_id": batch_id,
        }
        for t in trials if "protocolSection" in t
    ]
    with engine.begin() as conn:
        result = conn.execute(
            text("""
            INSERT INTO raw.clinical_trials (nct_id, raw_json, batch_id)
            VALUES (:nct_id, :raw_json::jsonb, :batch_id)
            ON CONFLICT (nct_id) DO UPDATE SET
                raw_json = EXCLUDED.raw_json,
                ingested_at = NOW(),
                is_processed = FALSE,
                batch_id = EXCLUDED.batch_id
            """),
            rows
        )
    return result.rowcount