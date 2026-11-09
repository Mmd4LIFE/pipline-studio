"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { Shell } from "@/components/shell";
import { api } from "@/lib/api";

const SqlEditor = dynamic(() => import("@/components/sql-editor").then((mod) => mod.SqlEditor), {
  ssr: false,
});

const DEFAULT_SQL = `SELECT
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
    CAST(ms.created_at AS DATE)`;

const DEFAULT_MAPPING = {
  id: "id",
  first_name: "first_name",
  date_day: "date_day",
  match_count: "match_count",
  min_place: "min_place",
};

export default function NewJobPage() {
  const router = useRouter();
  const [name, setName] = useState("Ludo Daily User Stats");
  const [description, setDescription] = useState("Load daily user match statistics into warehouse.analytics");
  const [sql, setSql] = useState(DEFAULT_SQL);
  const [cron, setCron] = useState("0 3 * * *");
  const [runImmediately, setRunImmediately] = useState(true);
  const [preview, setPreview] = useState<any>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  async function onValidate() {
    setBusy("validate");
    setError("");
    try {
      const result = await api.validate({
        source: { connection_id: "ludo_source", dialect: "postgresql", sql },
        destination: {
          connection_id: "warehouse",
          schema: "analytics",
          table: "daily_user_stats",
          create_table: false,
          column_mapping: DEFAULT_MAPPING,
        },
        preview: true,
      });
      setPreview(result);
      if ((result as any).formatted_sql) setSql((result as any).formatted_sql);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation failed");
    } finally {
      setBusy("");
    }
  }

  async function onCreate() {
    setBusy("create");
    setError("");
    try {
      const job = await api.createJob({
        name,
        description,
        tags: ["ludo", "analytics"],
        source: { connection_id: "ludo_source", dialect: "postgresql", sql },
        destination: {
          connection_id: "warehouse",
          schema: "analytics",
          table: "daily_user_stats",
          create_table: false,
          column_mapping: DEFAULT_MAPPING,
        },
        load: { mode: "full_refresh", write_batch_size: 2000, query_timeout_seconds: 300, max_rows: 2000000 },
        schedule: {
          cron,
          timezone: "Asia/Tehran",
          catchup: false,
          max_active_runs: 1,
          retries: 2,
          retry_delay_seconds: 300,
          execution_timeout_seconds: 1200,
        },
        run_immediately: runImmediately,
      });
      await api.deploy(job.id, runImmediately);
      router.push(`/jobs/${job.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setBusy("");
    }
  }

  return (
    <Shell>
      <h1 className="mb-1 text-2xl font-semibold">Create job</h1>
      <p className="mb-6 text-sm text-slate-400">Validate a read-only SELECT, map it to analytics, then Create & Start.</p>
      <div className="grid gap-6 lg:grid-cols-[1.4fr_0.8fr]">
        <section className="space-y-4 rounded-2xl border border-line bg-panel p-5">
          <label className="block text-sm">
            Name
            <input className="mt-1 w-full rounded-lg border border-line bg-ink px-3 py-2" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="block text-sm">
            Description
            <input className="mt-1 w-full rounded-lg border border-line bg-ink px-3 py-2" value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>
          <div>
            <div className="mb-2 flex items-center justify-between text-sm">
              <span>Source SQL</span>
              <span className="text-slate-500">ludo_source · read-only</span>
            </div>
            <SqlEditor value={sql} onChange={setSql} />
          </div>
          {error ? <p className="text-sm text-rose-300">{error}</p> : null}
          <div className="flex gap-3">
            <button onClick={onValidate} disabled={!!busy} className="rounded-lg border border-line px-4 py-2">
              {busy === "validate" ? "Validating…" : "Validate & preview"}
            </button>
            <button onClick={onCreate} disabled={!!busy} className="rounded-lg bg-accent px-4 py-2 font-semibold text-ink">
              {busy === "create" ? "Publishing…" : "Create & Start"}
            </button>
          </div>
        </section>
        <aside className="space-y-4">
          <div className="rounded-2xl border border-line bg-panel p-5 text-sm">
            <h2 className="mb-3 font-semibold">Destination</h2>
            <p>warehouse → analytics.daily_user_stats</p>
            <p className="mt-2 text-slate-400">Load: transactional full refresh</p>
            <label className="mt-4 block">
              Cron
              <input className="mt-1 w-full rounded-lg border border-line bg-ink px-3 py-2 font-mono" value={cron} onChange={(e) => setCron(e.target.value)} />
            </label>
            <p className="mt-2 text-slate-400">Timezone: Asia/Tehran · catchup off · max active runs 1</p>
            <label className="mt-4 flex items-center gap-2">
              <input type="checkbox" checked={runImmediately} onChange={(e) => setRunImmediately(e.target.checked)} />
              Run immediately after deploy
            </label>
          </div>
          <div className="rounded-2xl border border-line bg-panel p-5 text-sm">
            <h2 className="mb-3 font-semibold">Preview</h2>
            {preview?.preview ? (
              <div className="overflow-auto">
                <p className="mb-2 text-slate-400">
                  {preview.preview.row_count} rows · {preview.preview.duration_ms} ms
                </p>
                <table className="w-full text-xs">
                  <thead>
                    <tr>
                      {preview.preview.columns.map((col: { name: string }) => (
                        <th key={col.name} className="pr-3 text-left text-slate-400">
                          {col.name}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.preview.rows.slice(0, 8).map((row: Record<string, unknown>, idx: number) => (
                      <tr key={idx}>
                        {preview.preview.columns.map((col: { name: string }) => (
                          <td key={col.name} className="pr-3 py-1 font-mono">
                            {String(row[col.name] ?? "")}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-slate-500">Validate to inspect inferred columns and a 100-row sample.</p>
            )}
          </div>
        </aside>
      </div>
    </Shell>
  );
}
