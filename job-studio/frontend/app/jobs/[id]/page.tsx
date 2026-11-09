"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Shell } from "@/components/shell";
import { StatusBadge } from "@/components/status-badge";
import { api } from "@/lib/api";

export default function JobDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [tab, setTab] = useState<"overview" | "sql" | "runs" | "logs">("overview");
  const job = useQuery({ queryKey: ["job", id], queryFn: () => api.job(id), refetchInterval: 4000 });
  const runs = useQuery({ queryKey: ["runs", id], queryFn: () => api.runs(id), refetchInterval: 4000 });
  const latest = runs.data?.[0];
  const logs = useQuery({
    queryKey: ["logs", id, latest?.id],
    queryFn: () => api.logs(id, latest!.id),
    enabled: tab === "logs" && !!latest,
  });

  const config = (job.data?.config || {}) as any;

  return (
    <Shell>
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{job.data?.name || "Job"}</h1>
          <p className="text-sm text-slate-400">{job.data?.dag_id}</p>
        </div>
        <div className="flex gap-2">
          <button className="rounded-lg border border-line px-3 py-2 text-sm" onClick={() => api.run(id).then(() => job.refetch())}>
            Run now
          </button>
          <button className="rounded-lg border border-line px-3 py-2 text-sm" onClick={() => api.pause(id).then(() => job.refetch())}>
            Pause
          </button>
          <button className="rounded-lg border border-line px-3 py-2 text-sm" onClick={() => api.resume(id).then(() => job.refetch())}>
            Resume
          </button>
        </div>
      </div>
      <div className="mb-4 flex gap-2 text-sm">
        {(["overview", "sql", "runs", "logs"] as const).map((item) => (
          <button
            key={item}
            onClick={() => setTab(item)}
            className={`rounded-full px-3 py-1 ${tab === item ? "bg-accent text-ink" : "bg-white/5"}`}
          >
            {item}
          </button>
        ))}
      </div>
      {tab === "overview" ? (
        <div className="grid gap-4 md:grid-cols-3">
          <Card label="Desired / Airflow state">
            <StatusBadge value={job.data?.status} />
            {job.data?.last_error ? <p className="mt-2 text-sm text-rose-300">{job.data.last_error}</p> : null}
          </Card>
          <Card label="Destination">
            <p className="font-mono text-sm">{job.data?.destination_label}</p>
            <p className="text-slate-400">revision {job.data?.current_revision}</p>
          </Card>
          <Card label="Last run">
            <StatusBadge value={job.data?.last_run?.state} />
            <p className="mt-2 text-sm text-slate-300">{job.data?.last_run?.rows_written ?? "—"} rows</p>
          </Card>
        </div>
      ) : null}
      {tab === "sql" ? (
        <pre className="overflow-auto rounded-2xl border border-line bg-panel p-5 font-mono text-sm">
          {config?.source?.sql}
        </pre>
      ) : null}
      {tab === "runs" ? (
        <div className="overflow-hidden rounded-2xl border border-line bg-panel">
          <table className="w-full text-left text-sm">
            <thead className="bg-white/5 text-slate-400">
              <tr>
                {["Run", "State", "Duration", "Rows read", "Rows written", "Error"].map((h) => (
                  <th key={h} className="px-4 py-3">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(runs.data || []).map((run) => (
                <tr key={run.id} className="border-t border-line/80">
                  <td className="px-4 py-3 font-mono text-xs">{run.airflow_run_id}</td>
                  <td className="px-4 py-3">
                    <StatusBadge value={run.state} />
                  </td>
                  <td className="px-4 py-3">{run.duration_ms ? `${Math.round(run.duration_ms / 1000)}s` : "—"}</td>
                  <td className="px-4 py-3">{run.rows_read ?? "—"}</td>
                  <td className="px-4 py-3">{run.rows_written ?? "—"}</td>
                  <td className="px-4 py-3 text-rose-300">{run.error_summary || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {tab === "logs" ? (
        <div className="space-y-4">
          {(logs.data || []).map((item) => (
            <div key={item.task_id} className="rounded-2xl border border-line bg-panel p-4">
              <div className="mb-2 flex items-center justify-between text-sm">
                <span className="font-medium">{item.task_id}</span>
                <StatusBadge value={item.state} />
              </div>
              <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap font-mono text-xs text-slate-300">
                {item.content}
              </pre>
            </div>
          ))}
        </div>
      ) : null}
    </Shell>
  );
}

function Card({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-line bg-panel p-5">
      <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">{label}</p>
      {children}
    </div>
  );
}
