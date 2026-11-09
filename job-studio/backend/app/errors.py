from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.airflow_client import AirflowUnavailable
from app.services.sql_preview import ConnectionFailed, QueryTimeout
from app.services.sql_validator import SqlValidationError


class AppError(Exception):
    def __init__(self, error_type: str, message: str, status_code: int = 400):
        self.error_type = error_type
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def register_errors(app: FastAPI) -> None:
    @app.exception_handler(SqlValidationError)
    async def validation_handler(_: Request, exc: SqlValidationError):
        return JSONResponse(
            status_code=400,
            content={"error_type": "validation_error", "message": str(exc)},
        )

    @app.exception_handler(ConnectionFailed)
    async def conn_handler(_: Request, exc: ConnectionFailed):
        return JSONResponse(
            status_code=502,
            content={"error_type": "connection_failed", "message": str(exc)},
        )

    @app.exception_handler(QueryTimeout)
    async def timeout_handler(_: Request, exc: QueryTimeout):
        return JSONResponse(
            status_code=408,
            content={"error_type": "query_timeout", "message": str(exc)},
        )

    @app.exception_handler(AirflowUnavailable)
    async def airflow_handler(_: Request, exc: AirflowUnavailable):
        return JSONResponse(
            status_code=503,
            content={"error_type": "airflow_unavailable", "message": str(exc)},
        )

    @app.exception_handler(AppError)
    async def app_handler(_: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error_type": exc.error_type, "message": exc.message},
        )

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"error_type": "internal_error", "message": "Unexpected server error"},
        )
