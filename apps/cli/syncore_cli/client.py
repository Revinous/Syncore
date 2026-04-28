from __future__ import annotations

from typing import Any

import httpx


class SyncoreApiError(RuntimeError):
    pass


class SyncoreApiClient:
    def __init__(self, api_url: str, timeout_seconds: float = 10.0) -> None:
        self._api_url = api_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
        url = f"{self._api_url}{path}"
        try:
            response = httpx.request(
                method, url, json=payload, timeout=self._timeout_seconds
            )
        except httpx.HTTPError as error:
            raise SyncoreApiError(
                f"Could not reach Syncore API at {self._api_url}: {error}"
            ) from error

        content_type = response.headers.get("content-type", "")
        data: Any
        if "application/json" in content_type:
            data = response.json()
        else:
            data = response.text

        if response.status_code >= 400:
            raise SyncoreApiError(
                f"{response.status_code} {response.reason_phrase}: {data}"
            )

        return data

    def health(self) -> Any:
        return self._request("GET", "/health")

    def services_health(self) -> Any:
        return self._request("GET", "/health/services")

    def dashboard_summary(self) -> Any:
        return self._request("GET", "/dashboard/summary")

    def list_workspaces(self) -> Any:
        return self._request("GET", "/workspaces")

    def create_workspace(self, payload: dict[str, Any]) -> Any:
        return self._request("POST", "/workspaces", payload)

    def get_workspace(self, workspace_id: str) -> Any:
        return self._request("GET", f"/workspaces/{workspace_id}")

    def scan_workspace(self, workspace_id: str) -> Any:
        return self._request("POST", f"/workspaces/{workspace_id}/scan")

    def list_workspace_files(self, workspace_id: str) -> Any:
        return self._request("GET", f"/workspaces/{workspace_id}/files")

    def list_tasks(self, workspace_id: str | None = None) -> Any:
        if workspace_id:
            return self._request("GET", f"/tasks?workspace_id={workspace_id}")
        return self._request("GET", "/tasks")

    def create_task(self, payload: dict[str, Any]) -> Any:
        return self._request("POST", "/tasks", payload)

    def get_task(self, task_id: str) -> Any:
        return self._request("GET", f"/tasks/{task_id}")

    def list_agent_runs(self) -> Any:
        return self._request("GET", "/agent-runs")

    def create_agent_run(self, payload: dict[str, Any]) -> Any:
        return self._request("POST", "/agent-runs", payload)

    def get_agent_run_result(self, run_id: str) -> Any:
        return self._request("GET", f"/agent-runs/{run_id}/result")

    def list_task_events(self, task_id: str) -> Any:
        return self._request("GET", f"/tasks/{task_id}/events")

    def create_project_event(self, payload: dict[str, Any]) -> Any:
        return self._request("POST", "/project-events", payload)

    def list_project_events(self, limit: int = 50) -> Any:
        return self._request("GET", f"/project-events?limit={limit}")

    def list_task_batons(self, task_id: str) -> Any:
        return self._request("GET", f"/tasks/{task_id}/baton-packets")

    def latest_task_baton(self, task_id: str) -> Any:
        return self._request("GET", f"/tasks/{task_id}/baton-packets/latest")

    def route_next_action(self, payload: dict[str, Any]) -> Any:
        return self._request("POST", "/routing/next-action", payload)

    def get_task_routing(self, task_id: str) -> Any:
        return self._request("GET", f"/tasks/{task_id}/routing")

    def generate_digest(self, payload: dict[str, Any]) -> Any:
        return self._request("POST", "/analyst/digest", payload)

    def get_task_digest(self, task_id: str) -> Any:
        return self._request("GET", f"/tasks/{task_id}/digest")

    def diagnostics(self) -> Any:
        return self._request("GET", "/diagnostics")

    def diagnostics_config(self) -> Any:
        return self._request("GET", "/diagnostics/config")

    def diagnostics_routes(self) -> Any:
        return self._request("GET", "/diagnostics/routes")

    def execute_run(self, payload: dict[str, Any]) -> Any:
        return self._request("POST", "/runs/execute", payload)

    def autonomy_scan_once(self, limit: int = 50) -> Any:
        return self._request("POST", f"/autonomy/scan-once?limit={limit}")

    def autonomy_run_task(self, task_id: str) -> Any:
        return self._request("POST", f"/autonomy/tasks/{task_id}/run")

    def autonomy_approve_task(self, task_id: str, reason: str | None = None) -> Any:
        return self._request(
            "POST",
            f"/autonomy/tasks/{task_id}/approve",
            {"reason": reason} if reason is not None else {},
        )

    def autonomy_reject_task(self, task_id: str, reason: str | None = None) -> Any:
        return self._request(
            "POST",
            f"/autonomy/tasks/{task_id}/reject",
            {"reason": reason} if reason is not None else {},
        )
