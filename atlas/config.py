import os
from dataclasses import dataclass


def _inteiro(nome, padrao, minimo=1):
    try:
        return max(minimo, int(os.getenv(nome, padrao)))
    except ValueError:
        return padrao


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    gemini_model: str
    max_upload_bytes: int
    max_rows: int
    max_columns: int
    max_message_chars: int
    artifact_ttl_hours: int
    rate_limit_per_minute: int
    send_data_samples: bool
    max_pending_tasks: int

    @classmethod
    def from_env(cls):
        return cls(
            gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
            max_upload_bytes=_inteiro("MAX_UPLOAD_MB", 10) * 1024 * 1024,
            max_rows=_inteiro("MAX_DATASET_ROWS", 1_000_000),
            max_columns=_inteiro("MAX_DATASET_COLUMNS", 1_000),
            max_message_chars=_inteiro("MAX_MESSAGE_CHARS", 3_000),
            artifact_ttl_hours=_inteiro("ARTIFACT_TTL_HOURS", 24),
            rate_limit_per_minute=_inteiro("RATE_LIMIT_PER_MINUTE", 60),
            send_data_samples=os.getenv("SEND_DATA_SAMPLES", "false").lower() == "true",
            max_pending_tasks=_inteiro("MAX_PENDING_TASKS", 4),
        )

    def public_status(self):
        return {
            "gemini_configurado": bool(self.gemini_api_key),
            "modelo": self.gemini_model,
            "envio_amostras": self.send_data_samples,
        }
