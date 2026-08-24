import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.models import (
    IntentContract,
    TransactionProposal,
    VerificationResult,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "intentlock.db"


def initialize_database(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> Path:
    database_path = Path(db_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS verification_records (
                receipt_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                decision TEXT NOT NULL,
                intent_json TEXT NOT NULL,
                transaction_json TEXT NOT NULL,
                result_json TEXT NOT NULL
            )
            """
        )
        connection.commit()

    return database_path


def record_verification(
    intent: IntentContract,
    transaction: TransactionProposal,
    result: VerificationResult,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> str:
    database_path = initialize_database(db_path)

    receipt_id = f"IL-{uuid4().hex[:12].upper()}"
    created_at = datetime.now(timezone.utc).isoformat()

    intent_json = json.dumps(
        intent.model_dump(mode="json"),
        sort_keys=True,
    )

    transaction_json = json.dumps(
        transaction.model_dump(mode="json"),
        sort_keys=True,
    )

    result_json = json.dumps(
        result.model_dump(mode="json"),
        sort_keys=True,
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO verification_records (
                receipt_id,
                created_at,
                decision,
                intent_json,
                transaction_json,
                result_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                receipt_id,
                created_at,
                result.decision.value,
                intent_json,
                transaction_json,
                result_json,
            ),
        )
        connection.commit()

    return receipt_id


def get_recent_records(
    limit: int = 20,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict]:
    database_path = initialize_database(db_path)

    safe_limit = max(1, min(limit, 100))

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT
                receipt_id,
                created_at,
                decision,
                intent_json,
                transaction_json,
                result_json
            FROM verification_records
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    records = []

    for row in rows:
        records.append(
            {
                "receipt_id": row["receipt_id"],
                "created_at": row["created_at"],
                "decision": row["decision"],
                "intent": json.loads(row["intent_json"]),
                "transaction": json.loads(
                    row["transaction_json"]
                ),
                "result": json.loads(row["result_json"]),
            }
        )

    return records