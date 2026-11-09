from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    studio_secret_key: str
    studio_admin_email: str = "admin@localhost"
    studio_admin_password: str
    studio_database_url: str
    studio_session_cookie: str = "studio_session"
    studio_csrf_cookie: str = "studio_csrf"
    studio_preview_max_rows: int = 100
    studio_preview_timeout_seconds: int = 15
    studio_max_rows: int = 2_000_000
    studio_statement_timeout_ms: int = 300_000

    ludo_db_name: str = "ludo"
    ludo_etl_password: str
    warehouse_db: str = "warehouse"
    warehouse_user: str = "warehouse_user"
    warehouse_password: str

    airflow_api_base_url: str = "http://airflow-webserver:8080/api/v1"
    airflow_api_username: str = "studio_api"
    airflow_api_password: str

    managed_jobs_dir: str = "/opt/airflow/managed-jobs"

    def source_dsn(self, connection_id: str) -> str:
        if connection_id == "ludo_source":
            return (
                f"postgresql://etl_reader:{self.ludo_etl_password}"
                f"@ludo-db:5432/{self.ludo_db_name}"
            )
        raise KeyError(connection_id)

    def dest_dsn(self, connection_id: str) -> str:
        if connection_id == "warehouse":
            return (
                f"postgresql://{self.warehouse_user}:{self.warehouse_password}"
                f"@warehouse-db:5432/{self.warehouse_db}"
            )
        raise KeyError(connection_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()
