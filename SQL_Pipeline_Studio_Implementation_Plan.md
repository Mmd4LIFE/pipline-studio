# SQL Pipeline Studio — Product & Engineering Implementation Plan

**Status:** Implementation-ready specification  
**Version:** 1.0  
**Prepared:** 2026-11-09  
**Audience:** Cursor AI, software engineers, and the server owner  
**Target deployment:** `/root/mk-projects/datawarehouse` on the existing Ubuntu/Docker server

---

## 1. Product vision

Build **SQL Pipeline Studio**, a self-hosted web application that allows an authorized user to define, validate, deploy, run, schedule, and monitor PostgreSQL-to-PostgreSQL SQL ETL jobs **without manually writing an Airflow DAG**.

The user should be able to:

1. Select a **source** database connection (initially Ludo PostgreSQL).
2. Write a **read-only SQL query** in an editor, validate it, preview sample results, and inspect inferred column types.
3. Select a **destination** database, schema, and table (initially `warehouse.analytics`).
4. Choose a **load strategy** and its required settings (full refresh initially; incremental upsert later).
5. Choose a **schedule**, timezone, retry policy, timeout, and optional alert settings.
6. Click **Validate → Create & Start**.
7. See an automatically registered Airflow DAG, its first run, task logs, row counts, run history, and failures directly in the application.
8. Later edit, pause, resume, run on demand, duplicate, and archive the job.

### North-star user story

> As a data analyst, I can paste a PostgreSQL SELECT query, choose `analytics.daily_user_stats`, schedule the pipeline to run at 03:00 Asia/Tehran, and have a working Airflow DAG with an initial run and visible load metrics, without touching Python, Docker, or the Airflow UI.

### Explicit non-goals for the MVP

- General-purpose arbitrary Python/Bash DAG editing.
- Arbitrary SQL writes against the source.
- Cross-engine transformation or CDC streaming.
- Kafka, Spark, dbt, distributed workers, complex DAG graph editing, or a full data catalog.
- Letting ordinary users configure arbitrary network hosts or privileged credentials.

**Principle:** Build a **declarative pipeline control plane**, not a general remote-code-execution interface.

---

## 2. Existing infrastructure (do not replace)

| Component | Existing state / convention |
|---|---|
| Ubuntu server | Docker Engine + Docker Compose, project root `/root/mk-projects` |
| Data warehouse project | `/root/mk-projects/datawarehouse` |
| Airflow | `apache/airflow:2.10.5`, `LocalExecutor` |
| Airflow webserver | `datawarehouse-airflow-webserver-1`, host `127.0.0.1:8085` → container `8080` |
| Airflow scheduler | `datawarehouse-airflow-scheduler-1` |
| Airflow metadata PostgreSQL | `datawarehouse-airflow-db-1` (do **not** store Studio app data here) |
| Warehouse PostgreSQL | `datawarehouse-warehouse-db-1`, host `127.0.0.1:5435` → container `5432` |
| Ludo PostgreSQL | `ludo-db-1`, PostgreSQL 16 |
| Metabase | Existing `metabase` container, host `127.0.0.1:3001` |
| Airflow subdomain | `airflow.mammad.site` through Cloudflare Tunnel |
| Existing business data example | `analytics.daily_user_stats` loaded from `users` + `match_seats` |

**Compatibility requirement:** The initial implementation must target **Airflow 2.10.5 stable REST API (`/api/v1`)**, not Airflow 3's public API. Do not upgrade Airflow as part of the MVP.

**Infrastructure rule:** Never run `docker compose down -v`, rename existing services, replace the warehouse, or change unrelated Ludo/Metabase containers. Take backups and test Compose diffs before deploying.

---

## 3. Recommended application stack

| Layer | Choice | Reason |
|---|---|---|
| Frontend | Next.js + TypeScript + Tailwind CSS + shadcn/ui | Fast, responsive management UI |
| SQL editor | CodeMirror 6 (`sql` language extension) | Highlighting, keyboard support, preview/test workflow |
| Data fetching | TanStack Query | Poll deployment and run status |
| Backend API | FastAPI + Pydantic v2 | Typed REST endpoints, validation, Python/PostgreSQL ecosystem |
| ORM & migrations | SQLAlchemy 2 + Alembic | Durable app metadata |
| Studio metadata DB | Separate **`pipeline_studio` database in the existing warehouse PostgreSQL instance** | Avoids another PostgreSQL server while keeping application data distinct from `warehouse` and Airflow metadata |
| DB access | psycopg / SQLAlchemy; PostgreSQL COPY streaming where possible | Efficient, bounded-memory loads |
| Airflow integration | Airflow 2.10.5 stable REST API + declarative DAG factory | No docker socket or arbitrary generated Python |
| Job definitions | Validated JSON specs, versioned, atomically published to shared volume | Deterministic DAG creation and auditability |
| SQL parsing | `sqlglot` PostgreSQL dialect plus database-enforced read-only privileges | Defense in depth; parser alone cannot enforce safety |
| App auth | Server-side sessions, Argon2id, CSRF protection; Cloudflare Access before public exposure | Protect an app that can run expensive queries and schedule jobs |
| Deployment | Additional Compose services behind existing Cloudflare Tunnel | Reuse current server without exposing service ports publicly |
| Tests | pytest, pytest-asyncio, Playwright, PostgreSQL integration tests | Regression confidence for lifecycle, SQL, and permissions |

For a single trusted operator, start with one admin account and simple roles, but design the schema so multiple users and RBAC can be added later.

---

## 4. High-level architecture

```text
Browser
  |
  v
Cloudflare Access (recommended) -> HTTPS: studio.mammad.site
  |
  v
[Next.js frontend]  --->  [FastAPI / control plane]
                               |       |       |
                               |       |       +--> Studio metadata DB
                               |       |            (pipeline_studio)
                               |       |
                               |       +--> Airflow 2.10.5 REST API
                               |            (discovery, unpause,
                               |             trigger, status, logs)
                               |
                               +--> [Atomic spec publisher]
                                      |
                           shared managed-jobs volume
                                      |
                           [Airflow DAG factory]
                                      |
                           [Airflow scheduler/executor]
                                      |
                              [Trusted ETL runner]
                                  /        \
                         read-only       scoped write
                         Ludo PG            |
                                           v
                                  Warehouse PostgreSQL
                                   analytics.* tables
                                           |
                                           v
                                        Metabase
```

### Critical separation of responsibilities

- **Frontend:** collects configuration; never receives raw database passwords, Airflow service credentials, or host filesystem access.
- **Studio API:** owns users, connection references, job definitions, validation, publishing, and Airflow API orchestration.
- **Airflow:** owns scheduling, execution, retries, and task/run state.
- **ETL runner:** executes only approved SQL read-only against the source and writes only to an approved destination.
- **Warehouse:** stores final business tables; not the Studio's workflow-state engine.
- **Studio metadata DB:** is the source of truth for the job definition, desired state, and revisions.

### Why not generate free-form Python per user?

Generating executable Python files from user input introduces code-injection, permission, audit, and maintenance risks. Instead, ship **one trusted DAG factory** and **one reusable ETL implementation**. The app writes strictly validated JSON specifications; the factory registers one DAG per published job. Airflow documents this configuration-driven dynamic DAG pattern.

---

## 5. MVP user experience

### Screen A — Jobs dashboard

Table columns:

`Name | Source | Destination | Schedule | Desired state | Airflow state | Last run | Duration | Rows loaded | Actions`

Actions: **New job**, **Run now**, **Pause**, **Resume**, **Edit**, **Duplicate**, **View runs**.

Filters: status, connection, schema, owner; search by name or DAG ID.

Status labels must distinguish:

- `draft`: not deployed.
- `validating`: connection/SQL/destination checks running.
- `publish_pending`: definition saved, awaiting filesystem publication.
- `deploying`: published but DAG not yet visible to Airflow.
- `active`: registered and enabled for scheduled execution.
- `paused`: registered but not scheduled.
- `failed_deployment`: cannot discover or activate DAG; error visible.
- `archived`: disabled, historical runs retained.

Do **not** show “Active” merely because the JSON file was written; verify actual Airflow state.

### Screen B — Create job wizard

1. **Basics**: name, slug (generated), description, owner, tags.
2. **Source**: choose an approved PostgreSQL connection; read-only connection validation.
3. **SQL**: CodeMirror editor, Format SQL, Validate, Preview first 100 rows, inferred column names/types, query timing. For MVP support a **single SELECT** or safe `WITH ... SELECT` statement only.
4. **Destination**: choose approved connection, schema, existing table or admin-approved create-table flow; show destination columns and mapping.
5. **Load strategy**:
   - MVP: **Full refresh** (atomic replacement within a transaction).
   - Later: **Upsert** (requires unique key/primary key), **Append**, **Watermark incremental**.
6. **Schedule**: manual-only or cron (wizard presets + advanced cron), IANA timezone (default `Asia/Tehran`), `catchup=false` by default, concurrency `1`, timeout, retries, retry delay, start date.
7. **Review & deploy**: summary, warnings (large table / no indexes / slow query), validate checks, **Create & Start** and optional **Run immediately** checkbox (default enabled).

### Screen C — Job detail

Tabs: **Overview**, **SQL**, **Runs**, **Logs**, **Configuration**, **Versions**, **Audit**.

Show job revision, immutable DAG ID, next scheduled run, last success/failure, number of rows, source execution time, load time, error summary, and deep link to Airflow.

### Screen D — Connections (admin-only)

List named connections, engine type, read-only/write capability, whether a test passed, owner, and last test time. Initially import the already configured Airflow connections:

- `ludo_source`
- `warehouse`

Avoid storing plaintext passwords in the Studio metadata DB. For MVP, references to Airflow Connections or server-managed secrets are enough. Adding arbitrary new connection credentials in the UI is a later phase requiring secure secrets storage, RBAC, and host/network allowlists.

---

## 6. Job definition contract

A job is an **immutable revision** plus a pointer to the currently published revision.

Example spec (illustrative; no real credentials included):

```json
{
  "schema_version": 1,
  "job_id": "job_01_demo",
  "revision": 1,
  "name": "Ludo Daily User Stats",
  "dag_id": "studio_ludo_daily_user_stats",
  "source": {
    "connection_id": "ludo_source",
    "dialect": "postgresql",
    "sql": "SELECT u.id, u.first_name, CAST(ms.created_at AS DATE) AS date_day, COUNT(ms.id) AS match_count, MIN(ms.place) AS min_place FROM users u JOIN match_seats ms ON ms.user_id = u.id GROUP BY u.id, u.first_name, CAST(ms.created_at AS DATE)"
  },
  "destination": {
    "connection_id": "warehouse",
    "schema": "analytics",
    "table": "daily_user_stats",
    "create_table": false,
    "column_mapping": {
      "id": "id",
      "first_name": "first_name",
      "date_day": "date_day",
      "match_count": "match_count",
      "min_place": "min_place"
    }
  },
  "load": {
    "mode": "full_refresh",
    "write_batch_size": 2000,
    "query_timeout_seconds": 300,
    "max_rows": 2000000
  },
  "schedule": {
    "cron": "0 3 * * *",
    "timezone": "Asia/Tehran",
    "catchup": false,
    "max_active_runs": 1,
    "retries": 2,
    "retry_delay_seconds": 300,
    "execution_timeout_seconds": 1200
  },
  "alerts": {
    "enabled": false
  }
}
```

**Design requirements:**

- Job ID and DAG ID are stable forever; display name can change.
- Validate identifiers with restrictive allowlists; quote PostgreSQL schema/table/column names using driver-supported identifier quoting, not string concatenation.
- SQL is **data**, not Python/Jinja/template code. Never interpolate arbitrary user-controlled SQL into command strings or an Airflow Python module.
- Treat timezone explicitly. For `TIMESTAMPTZ`, display what timezone applies to `CAST(created_at AS DATE)`; do not silently reinterpret daily boundaries.
- Avoid a bare `ORDER BY` in extraction when not needed, unless deterministic ordering is intentionally required.
- Store the full spec in revision history and include a content hash.
- Use Pydantic validators plus DB constraints for schema, schedule, load mode, limits, and ids.

---

## 7. Airflow integration design

### 7.1 Static DAG factory, dynamic DAG instances

Ship a trusted file such as:

`/root/mk-projects/datawarehouse/dags/studio_managed_jobs.py`

The factory:

1. Reads `*.json` from a **shared, read-only-to-Airflow** manifest directory such as `/opt/airflow/managed-jobs/current/`.
2. Rejects malformed specs and records actionable import/log errors without crashing all other jobs.
3. Sorts job specs by `dag_id` to ensure deterministic DAG creation.
4. Registers one DAG per active, valid spec using Airflow 2.10.5's `DAG` or `@dag` APIs.
5. Uses only trusted task implementations; never imports user code.
6. Sets `is_paused_upon_creation=True` and leaves unpausing to the control-plane deployment flow.
7. Uses `get_parsing_context()` as an optimization once the number of jobs warrants it.

The spec publisher writes an immutable file to `revisions/{job_id}/{revision}.json`, then atomically updates `current/{job_id}.json` using temp-file + `os.replace()` within the same filesystem, with `fsync` where appropriate.

**Important:** Airflow DAG discovery is eventually consistent. The backend must poll the API until the DAG appears, with timeout and clear failure handling. Do not promise instant creation.

### 7.2 Deployment lifecycle (Create & Start)

```text
User submits form
    |
    v
Validate policy -> validate source SQL -> preview columns
    |
    v
Validate destination, permission, and mapping
    |
    v
Commit job + immutable revision in Studio DB
    |
    v
Publisher writes spec atomically; publish event is audited
    |
    v
Poll Airflow GET /api/v1/dags/{dag_id}
    |
    +-- not found yet -> keep deploying, retry with backoff
    +-- timeout -> failed_deployment (reconcilable/retryable)
    |
    v
PATCH /api/v1/dags/{dag_id} with is_paused=false
    |
    v
If 'Run immediately': POST /api/v1/dags/{dag_id}/dagRuns
    |
    v
Save run_id; UI polls runs/status and metrics
```

Use a persistent reconciliation process that retries publication / DAG detection / activation after API restarts. All operations must be **idempotent**. A retry must not create multiple initial runs; use a deterministic `dag_run_id` or a stored trigger-operation ID and handle API `409 Conflict` as a potentially already-created run.

### 7.3 Airflow API adapter (v2.10.5)

The **backend only** communicates with Airflow's REST API over a private Docker network.

Minimum methods:

- `GET /api/v1/dags/{dag_id}` — confirm DAG registered.
- `PATCH /api/v1/dags/{dag_id}` — pause/unpause.
- `POST /api/v1/dags/{dag_id}/dagRuns` — trigger initial/manual run.
- `GET /api/v1/dags/{dag_id}/dagRuns` — list runs.
- `GET /api/v1/dags/{dag_id}/dagRuns/{dag_run_id}` — poll status.
- `GET /api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances` — retrieve task states.
- Airflow task logs endpoint (verify its exact API response and pagination against the deployed version) — display logs.

Configure an explicit compatible Airflow API auth backend (for example basic-auth backend, if permitted), a **dedicated least-privilege Airflow service account**, and backend-only secrets. Do not use the public Cloudflare hostname for service-to-service calls.

> A reference API integration must be tested against `apache/airflow:2.10.5` in an integration environment before implementing UI status flows.

### 7.4 DAG task structure (MVP)

```text
validate_runtime_config
        |
        v
extract_and_load (streaming; staged; atomic)
        |
        v
record_load_metrics
```

A single ETL task is acceptable in the first working slice. Split tasks only when it does not force large result sets through Airflow XCom. **Never put extracted row data in XCom**; put only counts, timestamps, and lightweight metadata there.

If a new job revision is published while a run is in progress, the run must use a **frozen revision** captured at execution start, rather than reading whatever current JSON happens to be available later.

---

## 8. ETL execution contracts

### 8.1 Source query safety

The query editor permits a single read-only `SELECT` (including approved `WITH ... SELECT`). Validate that:

- `sqlglot` successfully parses one PostgreSQL statement.
- No DDL/DML/`COPY`, `DO`, `CALL`, `EXECUTE`, `SELECT INTO`, or multiple statements are accepted.
- Source DB account is strictly **read-only** and only authorized schemas/tables are accessible.
- Source session uses a read-only transaction, `statement_timeout`, `lock_timeout`, bounded fetch size, and a configured time zone.
- Admin-configured max result rows, max query time, and source concurrency quotas are enforced.
- The app refuses suspicious functions or statement patterns according to policy; syntax validation alone is not a complete security boundary.

`EXPLAIN` without `ANALYZE` can be used for plans, but do not assume it proves a query is safe or cheap. Query preview runs with strict time/row limits and read-only credentials.

### 8.2 Destination writes

**MVP strategy: transactional full refresh.**

1. Validate that the source query columns match the destination mapping and data types.
2. Stream source results in bounded batches; use PostgreSQL COPY or parameterized batch inserts.
3. Load into a staging table for that run.
4. Verify row count, required columns, and optional primary-key uniqueness.
5. Within a destination transaction, replace the destination data and record load metrics.
6. Commit on success or roll back on failure; retain prior committed destination data on failure.

For a first release with a bounded dataset, a transactional `DELETE + INSERT` or `TRUNCATE + INSERT` can be chosen after assessing locks and write amplification. On busy analytical tables, prefer a carefully designed shadow-table / partition-switch approach **only after checking dependent views, indexes, ownership, permissions, and foreign keys**.

**Do not use unqualified table names.** Limit writable schema(s) and restrict the destination role to those schemas.

### 8.3 Future load modes

| Mode | Configuration | Semantics |
|---|---|---|
| Full refresh (MVP) | Existing target table, optional create-table flow | Exactly one committed snapshot per successful run |
| Append (Phase 2) | Append-only assurance, optional dedup key | Add rows without deleting old ones |
| Upsert (Phase 2) | One or more unique-key columns | `INSERT ... ON CONFLICT DO UPDATE` |
| Incremental watermark (Phase 3) | Source watermark column, lookback window, initial watermark, stable tie-breaker, delete policy | Only changed/new rows, with recoverable progress |

Watermarks advance **only after the destination commit succeeds**. Include replay/lookback handling for late-arriving records. Do not silently treat `created_at` as a change-data-capture column when updates can occur after creation.

---

## 9. Studio database schema (initial proposal)

Create a **new PostgreSQL database `pipeline_studio` in the existing `warehouse-db` Postgres instance** with its own login/permissions. This is *not* the `warehouse` database and *not* `airflow-db`.

Suggested tables:

| Table | Purpose | Essential columns |
|---|---|---|
| `users` | App identity | `id`, `email`, `password_hash`, `role`, `created_at`, `disabled_at` |
| `connection_refs` | Approved Airflow connection references | `id`, `name`, `airflow_conn_id`, `engine`, `capability`, `allowed_schemas`, `enabled` |
| `jobs` | Logical job and desired state | `id`, `slug`, `name`, `description`, `dag_id`, `owner_id`, `status`, `desired_enabled`, `current_revision_id`, timestamps |
| `job_revisions` | Immutable job configuration | `id`, `job_id`, `revision_no`, `config_json`, `sha256`, `created_by`, `created_at` |
| `deployments` | Published revision reconciliation | `id`, `job_id`, `revision_id`, `state`, `airflow_seen_at`, `last_error`, `attempt_count`, timestamps |
| `job_runs` | Cached/mirrored Airflow runs | `id`, `job_id`, `airflow_run_id`, `revision_id`, `state`, `started_at`, `ended_at`, `rows_read`, `rows_written`, `duration_ms`, `error_summary` |
| `audit_events` | Change tracking | `id`, `actor_id`, `entity_type`, `entity_id`, `action`, `before_json`, `after_json`, `created_at`, `request_id` |
| `outbox_events` | Durable publish/reconciliation triggers | `id`, `event_type`, `payload_json`, `status`, `attempts`, `next_attempt_at`, timestamps |

Requirements:

- Enforce unique `jobs.slug`, `jobs.dag_id`, `(job_id, revision_no)` and `(job_id, airflow_run_id)`.
- Use UTC timestamps in control-plane storage; render user-selected timezones in the UI.
- Do not duplicate or alter Airflow's own metadata tables.
- Do not persist database plaintext credentials, API tokens, or secrets in JSON specs, audit logs, or exceptions.
- Support an Alembic upgrade/downgrade migration workflow and migration tests.

---

## 10. Backend API design

Base path: `/api/v1` (Studio's API; independent of Airflow's `/api/v1`).

### Authentication and connections

| Method | Path | Behavior |
|---|---|---|
| `POST` | `/auth/login` | Login and create secure session |
| `POST` | `/auth/logout` | Invalidate session |
| `GET` | `/auth/me` | Current user and role |
| `GET` | `/connections` | List approved references, never raw secrets |
| `POST` | `/connections/{id}/test` | Authorized connectivity test, timeout-bound |

### Jobs and lifecycle

| Method | Path | Behavior |
|---|---|---|
| `GET` | `/jobs` | Paginated/filterable list |
| `POST` | `/jobs` | Create draft |
| `GET` | `/jobs/{id}` | Detail and current revision |
| `PATCH` | `/jobs/{id}` | Edit draft / create new immutable revision |
| `POST` | `/jobs/validate` | Validate a proposed configuration and optionally preview SQL |
| `POST` | `/jobs/{id}/deploy` | Publish revision and enqueue reconciliation |
| `POST` | `/jobs/{id}/run` | Trigger idempotent manual execution |
| `POST` | `/jobs/{id}/pause` | Pause Airflow DAG |
| `POST` | `/jobs/{id}/resume` | Unpause Airflow DAG |
| `POST` | `/jobs/{id}/archive` | Pause, retire desired state, preserve history |
| `GET` | `/jobs/{id}/revisions` | Revision list and diffs |
| `GET` | `/jobs/{id}/deployments` | Publication/discovery state |
| `GET` | `/jobs/{id}/runs` | Paginated Airflow-backed run list |
| `GET` | `/jobs/{id}/runs/{run_id}` | Run detail with metrics and task state |
| `GET` | `/jobs/{id}/runs/{run_id}/logs` | Sanitized/paginated logs |
| `GET` | `/system/health` | Readiness + external dependency checks |

API must return clear error types: `validation_error`, `permission_denied`, `connection_failed`, `destination_mismatch`, `deployment_timeout`, `airflow_unavailable`, `query_timeout`, `load_failed`.

Use idempotency keys for **deploy**, **run**, and similar mutations. Return asynchronous operation IDs and poll endpoints for long-running validation or deployment; don't hold web requests open waiting for the scheduler.

---

## 11. Security requirements (MVP blockers)

1. **No arbitrary code:** user input is only data; no Python/Bash/container command customization.
2. **Strict source permissions:** read-only PostgreSQL role with schema grants; always use read-only transactions and timeouts.
3. **Least-privilege destination permissions:** dedicated `etl_writer`, restricted to specified database/schema; not the Postgres superuser.
4. **Credential separation:** frontend never sees DB passwords or Airflow service credentials; connection IDs are resolved server-side. Redact sensitive strings in logs and API responses.
5. **No Docker socket:** Studio must not mount `/var/run/docker.sock` or issue arbitrary `docker exec`.
6. **Network restrictions:** API can access only approved DB hosts and internal Airflow. Avoid user-specified arbitrary hostnames (SSRF, metadata-service access).
7. **Scoped filesystem writes:** Studio publisher may write only the managed manifest directory; it must not be allowed to overwrite trusted Airflow Python modules.
8. **Web security:** require authentication, CSRF protection for cookie-based sessions, secure/HttpOnly cookies, input validation, rate limiting, audit log.
9. **External access:** route via Cloudflare Tunnel and require Cloudflare Access; retain application authentication too.
10. **Operational safety:** max SQL runtime, preview result limit, total rows/bytes guardrails, retries, task concurrency limits, DB pool limits.
11. **Change control:** destructive target operations require a destination preview and explicit confirmation during creation/deployment.
12. **Kill switch:** ability to pause a job and prevent new Studio-initiated runs; document that pause does not automatically kill an already-running task.

The SQL editor is for **trusted analysts operating within authorized data-access policy**, not anonymous public users.

---

## 12. Deployment and filesystem layout

Suggested repo/worktree structure under the existing data warehouse project:

```text
/root/mk-projects/datawarehouse/
├── docker-compose.yml               # existing Airflow + PostgreSQL: preserve
├── docker-compose.studio.yml        # additional services / mounts (overlay)
├── .env                             # existing secrets: preserve; do not commit
├── dags/
│   ├── ludo_daily_user_stats.py     # existing hand-written DAG: preserve
│   └── studio_managed_jobs.py       # trusted static DAG factory
├── managed-jobs/                    # shared persisted specs, NOT git-tracked secrets
│   ├── current/                     # one published manifest per job
│   └── revisions/                   # immutable copies
├── job-studio/
│   ├── README.md
│   ├── .env.example
│   ├── backend/
│   │   ├── app/
│   │   │   ├── api/
│   │   │   ├── models/
│   │   │   ├── schemas/
│   │   │   ├── services/
│   │   │   │   ├── sql_validator.py
│   │   │   │   ├── airflow_client.py
│   │   │   │   ├── spec_publisher.py
│   │   │   │   └── deployment_reconciler.py
│   │   │   └── main.py
│   │   ├── alembic/
│   │   ├── tests/
│   │   └── Dockerfile
│   ├── frontend/
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/
│   │   ├── tests/
│   │   └── Dockerfile
│   └── docs/
│       ├── architecture.md
│       ├── operations.md
│       └── threat-model.md
└── logs/                             # existing Airflow logs: preserve
```

The Compose overlay should add `studio-api`, `studio-web`, and a `studio-reconciler` worker (can initially share the backend image). Extend the Airflow scheduler/webserver services with a **read-only bind mount** to the managed manifests. Mount the same directory **read-write only in the publisher process**. The existing ETL DAGs must remain operational.

**Networking:**

- Studio web: bind only to localhost, for example `127.0.0.1:8096`, after checking port availability.
- Studio API: internal Docker networking only; no public host port required.
- Internal Airflow: `http://airflow-webserver:8080` on the Compose network (verify actual service DNS).
- Warehouse: `warehouse-db:5432` on the Compose network.
- Source: `ludo-db:5432` on the shared analytics network.
- Optional public hostname: `studio.mammad.site` → Cloudflare Tunnel → `http://127.0.0.1:8096`; secure with Cloudflare Access **before** exposing.

**Permissions / development:** `/root/...` works for the existing server setup, but prefer a dedicated non-root deployment user and properly owned bind-mounted directories when practical. Never make managed spec directories world-writable.

**Important:** The provided Docker Compose configuration is a starting point, not an assured production security baseline. Perform hardening and backup tests before granting additional users access.

---

## 13. Implementation roadmap — small Cursor-friendly slices

### Phase 0 — Repository bootstrap and safety baseline

**Deliverables:** repo scaffolding, runtime inventory, architecture decisions, test harness, `.env.example`, read-only inspection of current Compose and network settings.

- [ ] Confirm current Airflow version, API auth backend, Airflow service DNS, bind mounts, Python packages, server RAM/disk.
- [ ] Inventory current Ludo source and warehouse grants without printing credentials.
- [ ] Create `job-studio` and Compose overlay, but do not deploy public service.
- [ ] Set up backend/frontend lint, type-check, unit tests, CI commands.
- [ ] Write migration/runbook and rollback procedures.

**Done when:** project builds/tests locally; no existing running containers are replaced; the development plan and invariants are documented.

### Phase 1 — Vertical slice: create → deploy → run one SQL job

**Deliverables:** a complete end-to-end flow **before** styling or expanding features.

- [ ] Implement Studio metadata DB and migrations for `jobs`, `job_revisions`, `deployments`, `outbox_events`, `job_runs`.
- [ ] Implement approved connections (`ludo_source`, `warehouse`) without plaintext secrets.
- [ ] Implement server-side source `SELECT` validator and preview with timeouts.
- [ ] Implement existing-table destination validation for `analytics.daily_user_stats`.
- [ ] Implement full-refresh streaming ETL and metrics.
- [ ] Implement JSON manifest publisher and trusted Airflow factory.
- [ ] Implement Airflow API adapter, reconciling DAG discovery, unpause, and trigger.
- [ ] Build a minimal web form and simple job/run status page.
- [ ] Demonstrate the Ludo daily-user-stats query from the UI end to end.

**Done when:** submit query and job settings → one DAG with stable ID appears → one initial run executes → data is present in `warehouse.analytics.daily_user_stats` → visible status/metrics → a second run does not duplicate data.

### Phase 2 — Usable product UI and operations

- [ ] Build all wizard steps, validation errors, SQL formatting, previews, and column mapping UI.
- [ ] Job list, search/filter, job detail, runs, logs, pause/resume, manual trigger.
- [ ] Job versions and revision comparison.
- [ ] Session auth, RBAC (Admin, Editor, Viewer), audit events.
- [ ] Scheduled reconciliation and clear error recovery.
- [ ] Alerting: optional email/webhook on failures with rate limits and redaction.

**Done when:** a non-developer authorized analyst can create, manage, and troubleshoot a job without SSH or editing Python.

### Phase 3 — Load modes and data quality

- [ ] Append and keyed upsert.
- [ ] Schema inference + guarded create-table wizard.
- [ ] Watermark incremental sync with lookback/replay.
- [ ] Data quality rules: null ratio, uniqueness, row count bounds, freshness, schema drift.
- [ ] Data lineage/source→target metadata and run-level comparison with previous runs.

**Done when:** reruns are idempotent, watermarks never skip after failure, and failed quality checks can prevent publishing an invalid snapshot.

### Phase 4 — Reliability and scale

- [ ] More engines (MySQL, ClickHouse, Trino) behind adapter interfaces; implement each only after compatible tests.
- [ ] Better tenant isolation, quotas, pool policies, and secrets backend.
- [ ] Pagination/virtualization, high job counts, caching, indexing, background task scalability.
- [ ] CI/CD, backup/restore drills, monitoring, alerts, upgrade playbook for Airflow 3 (separate migration project).

**Done when:** the platform scales to the agreed job count/volume and passes failure-injection and recovery tests.

---

## 14. Mandatory tests and acceptance scenarios

### End-to-end happy path

1. Create the `Ludo Daily User Stats` job using the sample configuration.
2. Validate the source connection and SQL preview.
3. Validate destination `analytics.daily_user_stats` column mapping.
4. Deploy and optionally trigger immediately.
5. Confirm the DAG exists using Airflow REST API and is unpaused.
6. Confirm one run transitions through queued/running to success.
7. Confirm warehouse row counts and no duplicate `(id, date_day)` keys.
8. Confirm the table remains queryable in existing Metabase.

### Failures and safety cases

- Invalid SQL / multiple statements / source `DELETE` / SQL injection attempts → rejected; no DAG published.
- Read-only source SQL that is too slow → canceled by timeout; proper error shown.
- Destination table missing/mismatched → explain before deploy.
- Airflow API unavailable during deployment → job shows deploying/failed_deployment, can reconcile later.
- Airflow DAG not parsed quickly → asynchronous status, no false success, eventual recovery.
- Publish process killed mid-write → old published spec remains valid; no partial JSON read.
- Studio API restarted during deployment → outbox/reconciler eventually completes.
- Trigger retried after network timeout → only one intended manual/initial DAG run.
- SQL job fails halfway through load → previous committed destination data remains intact.
- Source connection dropped mid-extract → no partially refreshed warehouse table.
- Two DAG runs overlap → concurrency/lock prevents corrupt load.
- Job edited during an active run → active run uses a frozen revision.
- Paused job → no newly scheduled runs; UI reflects Airflow state.
- Unauthorized user → cannot create, edit, see secrets, or trigger jobs.
- Existing Airflow DAGs and Ludo/Metabase remain fully operational.

### Minimum operational metrics

Capture per run: `queued_at`, `started_at`, `ended_at`, `duration_ms`, `rows_read`, `rows_written`, `bytes_written` where practical, `source_query_duration_ms`, `load_duration_ms`, `job_revision`, `dag_run_id`, `status`, and redacted error summary.

---

## 15. Initial milestones and priorities

| Milestone | Priority | Output | Gate |
|---|---|---|---|
| M0 | P0 | Safe repo + no-op deployment overlay | Existing workloads unchanged |
| M1 | P0 | Backend metadata + valid SQL preview | Read-only source enforcement proven |
| M2 | P0 | Reusable ETL runner + atomic full refresh | Rollback test passes |
| M3 | P0 | Spec publisher + dynamic DAG factory | One registered DAG per job |
| M4 | P0 | Airflow API orchestration + reconciliation | Create & Start survives retries |
| M5 | P0 | Minimal web form and runs page | End-to-end demo from browser |
| M6 | P1 | Complete wizard + logs + job management | Analyst usability test |
| M7 | P1 | Access control, auditing, deployment hardening | Threat model / smoke tests |
| M8 | P2 | Upsert + incremental + data quality | Backfill/late-data cases pass |

**Scope rule:** Don't start Phase 3 while Phase 1's happy path, failure recovery, and permissions are unverified.

---

## 16. Proposed first demo (seed job)

Use the source query below, including an explicit `u.first_name` group-by entry for PostgreSQL portability:

```sql
SELECT
    u.id,
    u.first_name,
    CAST(ms.created_at AS DATE) AS date_day,
    COUNT(ms.id) AS match_count,
    MIN(ms.place) AS min_place
FROM users AS u
JOIN match_seats AS ms
    ON ms.user_id = u.id
GROUP BY
    u.id,
    u.first_name,
    CAST(ms.created_at AS DATE)
```

Destination: `warehouse` → `analytics.daily_user_stats`.  
Schedule: `0 3 * * *` in `Asia/Tehran`.  
Load: `full_refresh`.  
On create: validate → deploy → unpause → trigger once.  
Existing table: preferred for MVP (do not auto-drop/recreate table).  
Safety: source `etl_reader`, destination restricted `etl_writer`, timeouts and row limit.

**Semantics:** `match_count` counts `match_seats` rows per user/day, not necessarily distinct matches. Date conversion uses the source session timezone if `created_at` is `timestamptz`, so establish the intended business timezone explicitly.

---

## 17. Cursor implementation instructions (copy/paste)

> You are implementing **SQL Pipeline Studio** using `SQL_Pipeline_Studio_Implementation_Plan.md` as the project specification. The project lives under `/root/mk-projects/datawarehouse/job-studio`, alongside existing, running Airflow 2.10.5 and PostgreSQL containers. Begin with **Phase 0 only**. Inspect the actual repo and Docker Compose files before changing anything. Preserve all current Airflow, Ludo, Metabase, PostgreSQL services, DAGs, volumes, credentials, and networking. Do not run destructive Docker commands or change production connections. Use FastAPI + Pydantic v2 + SQLAlchemy/Alembic for the backend and Next.js + TypeScript for the frontend. Implement a declarative, versioned JSON job-spec architecture with a **trusted, static Airflow DAG factory**; never generate Python from user SQL. Use Airflow 2.10.5 `/api/v1`, not Airflow 3 API. Start with `ludo_source` → `warehouse.analytics.daily_user_stats`, a single safe `SELECT`, transactional full-refresh loading, and a reliable Create & Start state machine. Enforce least-privilege DB accounts, read-only source transactions, query limits, never expose secrets, and no Docker socket mounts. After Phase 0, report changed files, commands run, tests and results, remaining risks, and exact next-slice checklist. Continue one phase at a time; do not claim tests passed unless they were executed.

### After Phase 0, use this follow-up prompt

> Implement **Phase 1, Milestones M1–M2 only** from the plan. Deliver Studio database models/migrations, approved connection references, server-side PostgreSQL SELECT validation and bounded preview, and a reusable transactional streaming full-refresh loader with tests. Do not yet implement frontend styling or Airflow deployment. Prove rollback on mid-load failure and show test output. No changes to the existing production datasets without explicit approval.

### After M1–M2, use this follow-up prompt

> Implement **Phase 1, Milestones M3–M5 only** from the plan. Add immutable JSON publisher, trusted dynamic DAG factory, Airflow 2.10.5 REST API client, idempotent deployment reconciliation, and a minimal create-job frontend. Demonstrate Create & Start using a disposable test target, then carefully integrate the existing daily-user-stats target. Preserve current DAGs. Include API integration tests and a complete rollback procedure.

---

## 18. Open design decisions for the implementation

The default decisions above are acceptable for a first implementation, but Cursor should document and verify:

1. **Credentials:** are `ludo_source` and `warehouse` Airflow Connections already configured and sufficient? If not, create service-specific accounts rather than reusing an admin role.
2. **App DB:** is a separate `pipeline_studio` database inside `warehouse-db` acceptable for backup/restore and permissions? (Recommended for MVP.)
3. **SQL preview:** initial max 100 rows, 15-second timeout; adjustable by admin only.
4. **Limits:** source statement timeout and row/byte quotas according to server capacity.
5. **Timezone:** daily rollups should be aligned with business definition of a day, not accidentally depend on server UTC.
6. **Load isolation:** one active run per job, destination write serialization; specify same-table behavior if two jobs use the same target.
7. **Schema creation:** existing destination tables only in Phase 1; auto-create after validation and explicit consent.
8. **Auth:** single-admin local authentication for private MVP; Cloudflare Access and role separation before other users get access.
9. **Domain:** `studio.mammad.site` is proposed but not provisioned; only activate after securing the app.

---

## 19. Official references

- Airflow 2.10.5 — Dynamic DAG Generation: https://airflow.apache.org/docs/apache-airflow/2.10.5/howto/dynamic-dag-generation.html
- Airflow 2.10.5 — Stable REST API: https://airflow.apache.org/docs/apache-airflow/2.10.5/stable-rest-api-ref.html
- Airflow 2.10.5 — Docker Compose: https://airflow.apache.org/docs/apache-airflow/2.10.5/howto/docker-compose/index.html
- Airflow 2.10.5 — Production Deployment: https://airflow.apache.org/docs/apache-airflow/2.10.5/administration-and-deployment/production-deployment.html
- Airflow 2.10.5 — Configuration Reference: https://airflow.apache.org/docs/apache-airflow/2.10.5/configurations-ref.html

These docs are version-specific on purpose. Reassess the architecture and API compatibility separately before any future Airflow major-version upgrade.
