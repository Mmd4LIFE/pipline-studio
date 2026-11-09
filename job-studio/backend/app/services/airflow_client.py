from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings


class AirflowUnavailable(RuntimeError):
    error_type = "airflow_unavailable"


class AirflowClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base = settings.airflow_api_base_url.rstrip("/")
        self.auth = (settings.airflow_api_username, settings.airflow_api_password)

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"{self.base}{path}"
        try:
            with httpx.Client(timeout=20.0, auth=self.auth) as client:
                response = client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise AirflowUnavailable("Airflow API is unavailable") from exc
        if response.status_code in (401, 403):
            raise AirflowUnavailable("Airflow API rejected Studio credentials")
        return response

    def health(self) -> bool:
        try:
            response = self._request("GET", "/health" if False else "/dags", params={"limit": 1})
            return response.status_code < 500
        except AirflowUnavailable:
            return False

    def get_dag(self, dag_id: str) -> dict[str, Any] | None:
        response = self._request("GET", f"/dags/{dag_id}")
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise AirflowUnavailable(f"Airflow DAG lookup failed ({response.status_code})")
        return response.json()

    def set_paused(self, dag_id: str, paused: bool) -> dict[str, Any]:
        response = self._request("PATCH", f"/dags/{dag_id}", json={"is_paused": paused})
        if response.status_code >= 400:
            raise AirflowUnavailable(f"Failed to update DAG pause state ({response.status_code})")
        return response.json()

    def trigger_run(self, dag_id: str, dag_run_id: str) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/dags/{dag_id}/dagRuns",
            json={"dag_run_id": dag_run_id},
        )
        if response.status_code == 409:
            existing = self.get_run(dag_id, dag_run_id)
            if existing:
                return existing
        if response.status_code >= 400:
            raise AirflowUnavailable(
                f"Failed to trigger DAG run ({response.status_code}): {response.text[:300]}"
            )
        return response.json()

    def get_run(self, dag_id: str, dag_run_id: str) -> dict[str, Any] | None:
        response = self._request("GET", f"/dags/{dag_id}/dagRuns/{dag_run_id}")
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise AirflowUnavailable(f"Failed to fetch DAG run ({response.status_code})")
        return response.json()

    def list_runs(self, dag_id: str, limit: int = 25) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            f"/dags/{dag_id}/dagRuns",
            params={"limit": limit, "order_by": "-execution_date"},
        )
        if response.status_code == 404:
            return []
        if response.status_code >= 400:
            raise AirflowUnavailable(f"Failed to list DAG runs ({response.status_code})")
        return response.json().get("dag_runs") or []

    def task_instances(self, dag_id: str, dag_run_id: str) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            f"/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances",
        )
        if response.status_code >= 400:
            return []
        return response.json().get("task_instances") or []

    def task_logs(self, dag_id: str, dag_run_id: str, task_id: str, try_number: int = 1) -> str:
        response = self._request(
            "GET",
            f"/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{try_number}",
            params={"full_content": True},
            headers={"Accept": "application/json"},
        )
        if response.status_code >= 400:
            return response.text[:4000]
        try:
            data = response.json()
        except ValueError:
            return response.text[:8000]
        if isinstance(data, dict):
            content = data.get("content")
            if isinstance(content, list):
                return "\n".join(str(item) for item in content)[:12_000]
            if isinstance(content, str):
                return content[:12_000]
        return str(data)[:12_000]
