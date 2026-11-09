# Operations

## Start

From `/root/mk-projects/datawarehouse`:

```bash
docker compose -f docker-compose.yml -f docker-compose.studio.yml up -d
```

Studio UI: `http://127.0.0.1:8096`  
Do not publish this port. Put Cloudflare Access in front before using a public hostname.

## Rollback

```bash
docker compose -f docker-compose.yml -f docker-compose.studio.yml stop studio-web studio-api studio-reconciler
# Airflow continues with previously published JSON specs. To disable Studio DAGs:
# pause them in Airflow or remove files under managed-jobs/current/
```

Never run `docker compose down -v`.

## Database

Studio metadata lives in database `pipeline_studio` on `warehouse-db`, not in Airflow metadata and not in `warehouse`.

## Logs

```bash
docker compose -f docker-compose.yml -f docker-compose.studio.yml logs -f studio-api studio-reconciler studio-web
```
