from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.connections import router as connections_router
from app.api.jobs import router as jobs_router
from app.api.system import router as system_router
from app.bootstrap import seed
from app.config import get_settings
from app.errors import register_errors


def run_migrations() -> None:
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings()
    run_migrations()
    seed()
    Path(get_settings().managed_jobs_dir, "current").mkdir(parents=True, exist_ok=True)
    Path(get_settings().managed_jobs_dir, "revisions").mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="SQL Pipeline Studio", version="1.0.0", lifespan=lifespan)
register_errors(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8096", "http://localhost:8096"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(connections_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(system_router, prefix="/api/v1")
