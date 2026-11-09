# Threat model (MVP)

Assets: Ludo source data, warehouse tables, Airflow scheduler, Studio session cookies.

Trust boundary: only an authenticated operator uses the UI. The SQL editor is not a public query interface.

Controls:

- User SQL is data. No generated Python, Bash, or container commands.
- Source queries are parsed with sqlglot and executed as read-only transactions with timeouts.
- Destination writes use identifier quoting and an approved schema/table allowlist.
- Studio does not mount the Docker socket.
- Publisher can write only `managed-jobs/`.
- Frontend never receives DSNs or Airflow passwords.
- Cookie sessions + CSRF header on mutating requests.
- Airflow API is reached over the private Compose network, not `airflow.mammad.site`.

Residual risk: the warehouse connection currently uses the existing warehouse role. A dedicated `etl_writer` should replace it before additional users are invited. Cloudflare Access is required before any public hostname is enabled.
