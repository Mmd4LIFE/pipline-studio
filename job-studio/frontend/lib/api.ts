export type Job = {
  id: string;
  slug: string;
  name: string;
  description?: string | null;
  dag_id: string;
  status: string;
  desired_enabled: boolean;
  current_revision?: number | null;
  config?: Record<string, unknown> | null;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
  source_name?: string | null;
  destination_label?: string | null;
  schedule_label?: string | null;
  last_run?: {
    state: string;
    airflow_run_id: string;
    ended_at?: string | null;
    duration_ms?: number | null;
    rows_written?: number | null;
  } | null;
};

export type ConnectionRef = {
  id: string;
  name: string;
  airflow_conn_id: string;
  engine: string;
  capability: string;
  allowed_schemas: string[];
  enabled: boolean;
  last_tested_at?: string | null;
  last_test_ok?: boolean | null;
};

export type Run = {
  id: string;
  airflow_run_id: string;
  state: string;
  queued_at?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  duration_ms?: number | null;
  rows_read?: number | null;
  rows_written?: number | null;
  error_summary?: string | null;
};

function csrfToken(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(/(?:^|; )studio_csrf=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const csrf = csrfToken();
  if (csrf) headers.set("X-CSRF-Token", csrf);
  const response = await fetch(path, {
    ...init,
    headers,
    credentials: "include",
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const message = data?.message || `Request failed (${response.status})`;
    throw new Error(message);
  }
  return data as T;
}

export const api = {
  me: () => request<{ id: string; email: string; role: string }>("/api/v1/auth/me"),
  login: (email: string, password: string) =>
    request("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request("/api/v1/auth/logout", { method: "POST" }),
  jobs: () => request<Job[]>("/api/v1/jobs"),
  job: (id: string) => request<Job>(`/api/v1/jobs/${id}`),
  createJob: (body: unknown) => request<Job>("/api/v1/jobs", { method: "POST", body: JSON.stringify(body) }),
  deploy: (id: string, runImmediately = true) =>
    request(`/api/v1/jobs/${id}/deploy?run_immediately=${runImmediately}`, { method: "POST" }),
  run: (id: string) => request(`/api/v1/jobs/${id}/run`, { method: "POST" }),
  pause: (id: string) => request(`/api/v1/jobs/${id}/pause`, { method: "POST" }),
  resume: (id: string) => request(`/api/v1/jobs/${id}/resume`, { method: "POST" }),
  archive: (id: string) => request(`/api/v1/jobs/${id}/archive`, { method: "POST" }),
  duplicate: (id: string) => request<Job>(`/api/v1/jobs/${id}/duplicate`, { method: "POST" }),
  validate: (body: unknown) => request("/api/v1/jobs/validate", { method: "POST", body: JSON.stringify(body) }),
  runs: (id: string) => request<Run[]>(`/api/v1/jobs/${id}/runs`),
  logs: (jobId: string, runId: string) =>
    request<{ task_id: string; state: string; content: string }[]>(`/api/v1/jobs/${jobId}/runs/${runId}/logs`),
  connections: () => request<ConnectionRef[]>("/api/v1/connections"),
  testConnection: (id: string) => request(`/api/v1/connections/${id}/test`, { method: "POST" }),
};
