"use client";

import { useQuery } from "@tanstack/react-query";
import { Shell } from "@/components/shell";
import { api } from "@/lib/api";

export default function ConnectionsPage() {
  const connections = useQuery({ queryKey: ["connections"], queryFn: api.connections });

  return (
    <Shell>
      <h1 className="mb-1 text-2xl font-semibold">Approved connections</h1>
      <p className="mb-6 text-sm text-slate-400">
        Studio stores references to Airflow connections. Secrets never leave the server.
      </p>
      <div className="grid gap-4 md:grid-cols-2">
        {(connections.data || []).map((conn) => (
          <div key={conn.id} className="rounded-2xl border border-line bg-panel p-5">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold">{conn.name}</h2>
              <span className="text-xs uppercase text-slate-400">{conn.capability}</span>
            </div>
            <p className="mt-1 font-mono text-sm text-slate-300">{conn.airflow_conn_id}</p>
            <p className="mt-2 text-sm text-slate-400">
              {conn.engine} · schemas: {(conn.allowed_schemas || []).join(", ")}
            </p>
            <button
              className="mt-4 rounded-lg border border-line px-3 py-1.5 text-sm"
              onClick={() => api.testConnection(conn.airflow_conn_id).then(() => connections.refetch())}
            >
              Test connection
            </button>
            <p className="mt-2 text-xs text-slate-500">
              Last test: {conn.last_tested_at || "never"} {conn.last_test_ok == null ? "" : conn.last_test_ok ? "· ok" : "· failed"}
            </p>
          </div>
        ))}
      </div>
    </Shell>
  );
}
