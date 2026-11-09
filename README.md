# SQL Pipeline Studio

Declarative PostgreSQL ETL control plane for the existing Airflow 2.10.5 / warehouse stack.

## Layout

- `job-studio/backend` — FastAPI control plane
- `job-studio/frontend` — Next.js UI
- `dags/studio_managed_jobs.py` — trusted DAG factory
- `dags/studio_etl.py` — trusted extract/load implementation
- `docker-compose.studio.yml` — overlay; does not replace warehouse services
- `SQL_Pipeline_Studio_Implementation_Plan.md` — product spec

## Local tests

```bash
cd job-studio/backend
pip install -r requirements.txt
pytest -q
```
