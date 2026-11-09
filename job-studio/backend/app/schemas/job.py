from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

LoadMode = Literal["full_refresh"]
JobStatus = Literal[
    "draft",
    "validating",
    "publish_pending",
    "deploying",
    "active",
    "paused",
    "failed_deployment",
    "archived",
]


class SourceConfig(BaseModel):
    connection_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    dialect: Literal["postgresql"] = "postgresql"
    sql: str = Field(min_length=10, max_length=50_000)


class DestinationConfig(BaseModel):
    connection_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    schema_name: str = Field(alias="schema", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    table: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    create_table: bool = False
    column_mapping: dict[str, str]

    model_config = {"populate_by_name": True}

    @field_validator("column_mapping")
    @classmethod
    def mapping_idents(cls, value: dict[str, str]) -> dict[str, str]:
        import re

        ident = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
        if not value:
            raise ValueError("column_mapping is required")
        for src, dst in value.items():
            if not ident.match(src) or not ident.match(dst):
                raise ValueError("column mapping keys/values must be identifiers")
        return value


class LoadConfig(BaseModel):
    mode: LoadMode = "full_refresh"
    write_batch_size: int = Field(default=2000, ge=100, le=20_000)
    query_timeout_seconds: int = Field(default=300, ge=5, le=3600)
    max_rows: int = Field(default=2_000_000, ge=1, le=20_000_000)


class ScheduleConfig(BaseModel):
    cron: str | None = None
    timezone: str = "Asia/Tehran"
    catchup: bool = False
    max_active_runs: int = Field(default=1, ge=1, le=1)
    retries: int = Field(default=2, ge=0, le=8)
    retry_delay_seconds: int = Field(default=300, ge=10, le=3600)
    execution_timeout_seconds: int = Field(default=1200, ge=30, le=7200)

    @field_validator("cron")
    @classmethod
    def valid_cron(cls, value: str | None) -> str | None:
        if value in (None, "", "manual"):
            return None
        from croniter import croniter

        if not croniter.is_valid(value):
            raise ValueError("Invalid cron expression")
        return value


class JobSpecIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: SourceConfig
    destination: DestinationConfig
    load: LoadConfig = Field(default_factory=LoadConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    run_immediately: bool = True


class ValidateRequest(BaseModel):
    source: SourceConfig
    destination: DestinationConfig | None = None
    preview: bool = False


class JobCreate(JobSpecIn):
    pass


class JobPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    source: SourceConfig | None = None
    destination: DestinationConfig | None = None
    load: LoadConfig | None = None
    schedule: ScheduleConfig | None = None


class JobOut(BaseModel):
    id: str
    slug: str
    name: str
    description: str | None
    dag_id: str
    status: str
    desired_enabled: bool
    current_revision: int | None = None
    config: dict[str, Any] | None = None
    last_error: str | None = None
    created_at: str
    updated_at: str
    source_name: str | None = None
    destination_label: str | None = None
    schedule_label: str | None = None
    last_run: dict[str, Any] | None = None


class RunOut(BaseModel):
    id: str
    airflow_run_id: str
    state: str
    queued_at: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int | None = None
    rows_read: int | None = None
    rows_written: int | None = None
    error_summary: str | None = None
