# Architecture

SQL Pipeline Studio is a declarative control plane for PostgreSQL-to-PostgreSQL ETL. The browser never receives database or Airflow secrets. User SQL is stored as JSON and executed by one trusted Airflow DAG factory.

```
Browser → studio-web (:8096, localhost)
        → studio-api (FastAPI)
            → pipeline_studio DB on warehouse-db
            → Airflow REST API /api/v1
            → managed-jobs JSON publisher
        → studio-reconciler (outbox worker)
Airflow scheduler reads managed-jobs/current/*.json (read-only)
Trusted tasks in dags/studio_managed_jobs.py + dags/studio_etl.py
```

Existing Airflow, Ludo, Metabase, and warehouse services are unchanged aside from:

- a read-only bind mount of `managed-jobs` on the Airflow webserver and scheduler
- `AIRFLOW__API__AUTH_BACKENDS` including basic auth so the Studio API can call Airflow privately
