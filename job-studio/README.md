# SQL Pipeline Studio

Self-hosted control plane for PostgreSQL SQL ETL jobs. Analysts define a SELECT, pick an approved destination, and Studio publishes a JSON spec that a trusted Airflow 2.10.5 DAG factory turns into a scheduled job.

This directory is deployed as `/root/mk-projects/datawarehouse/job-studio` beside the existing warehouse Compose stack. See `docs/operations.md`.
