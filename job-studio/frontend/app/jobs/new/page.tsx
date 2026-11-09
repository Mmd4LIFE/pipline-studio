"use client";

import { useMemo, useState } from "react";
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

type Column = { name: string; type: string; nullable?: boolean; has_default?: boolean };

export default function NewJobPage() {
  const router = useRouter();
  const [name, setName] = useState("Ludo Daily User Stats");
  const [description, setDescription] = useState("Load daily user match statistics into warehouse.analytics");
  const [sql, setSql] = useState(DEFAULT_SQL);
  const [table, setTable] = useState("daily_user_stats");
  const [cron, setCron] = useState("0 3 * * *");
  const [runImmediately, setRunImmediately] = useState(true);
  const [preview, setPreview] = useState<any>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [requiredCols, setRequiredCols] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const sourceCols: Column[] = preview?.preview?.columns || [];
  const missingRequired = useMemo(
    () => requiredCols.filter((col) => !Object.values(mapping).includes(col)),
    [requiredCols, mapping],
  );

  function onSqlChange(value: string) {
    setSql(value);
    setPreview(null);
    setError("");
  }

  async function onValidate() {
    setBusy("validate");
    setError("");
    try {
      const result: any = await api.validate({
        source: { connection_id: "ludo_source", dialect: "postgresql", sql },
        destination: {
          connection_id: "warehouse",
          schema: "analytics",
          table,
          create_table: false,
        },
        preview: true,
      });
      setPreview(result);
      setMapping(result.column_mapping || {});
      setRequiredCols(result.required_destination_columns || []);
      if (result.formatted_sql) setSql(result.formatted_sql);
      const missing = (result.required_destination_columns || []).filter(
        (col: string) => !Object.values(result.column_mapping || {}).includes(col),
      );
      if (missing.length) {
        setError(
          `This SELECT cannot fill analytics.${table}. Missing required columns: ${missing.join(", ")}. Add them to the query.`,
        );
      }
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
      if (!preview) {
        throw new Error("Validate & preview first so Studio can map the actual query columns.");
      }
      const job = await api.createJob({
        name,
        description,
        tags: ["ludo", "analytics"],
        source: { connection_id: "ludo_source", dialect: "postgresql", sql },
        destination: {
          connection_id: "warehouse",
          schema: "analytics",
          table,
          create_table: false,
          column_mapping: mapping,
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
      <p className="mb-6 text-sm text-slate-400">
        Validate a read-only SELECT. Columns are mapped from the query result onto an existing analytics table.
      </p>
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
            <SqlEditor value={sql} onChange={onSqlChange} />
          </div>
          {error ? <p className="text-sm text-rose-300">{error}</p> : null}
          <div className="flex gap-3">
            <button onClick={onValidate} disabled={!!busy} className="rounded-lg border border-line px-4 py-2">
              {busy === "validate" ? "Validating…" : "Validate & preview"}
            </button>
            <button onClick={onCreate} disabled={!!busy || !!missingRequired.length} className="rounded-lg bg-accent px-4 py-2 font-semibold text-ink disabled:opacity-50">
              {busy === "create" ? "Publishing…" : "Create & Start"}
            </button>
          </div>
        </section>
        <aside className="space-y-4">
          <div className="rounded-2xl border border-line bg-panel p-5 text-sm">
            <h2 className="mb-3 font-semibold">Destination</h2>
            <p className="text-slate-400">Existing warehouse table. The job name does not create a new table.</p>
            <label className="mt-3 block">
              Table
              <input className="mt-1 w-full rounded-lg border border-line bg-ink px-3 py-2 font-mono" value={table} onChange={(e) => setTable(e.target.value)} />
            </label>
            <p className="mt-2 font-mono text-xs text-slate-400">warehouse.analytics.{table}</p>
            <p className="mt-2 text-slate-400">Load: transactional full refresh</p>
            {requiredCols.length ? (
              <p className="mt-2 text-slate-300">
                Required columns: <span className="font-mono">{requiredCols.join(", ")}</span>
              </p>
            ) : null}
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
            <h2 className="mb-3 font-semibold">Column mapping</h2>
            {sourceCols.length ? (
              <div className="space-y-2">
                {sourceCols.map((col) => (
                  <div key={col.name} className="flex items-center justify-between gap-2 font-mono text-xs">
                    <span>{col.name}</span>
                    <span className="text-slate-500">→</span>
                    <span>{mapping[col.name] || "unmapped"}</span>
                  </div>
                ))}
                {missingRequired.length ? (
                  <p className="text-rose-300">Still missing: {missingRequired.join(", ")}</p>
                ) : (
                  <p className="text-emerald-300">Required destination columns are mapped.</p>
                )}
              </div>
            ) : (
              <p className="text-slate-500">Validate to map query columns onto the destination table.</p>
            )}
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
