const COLORS: Record<string, string> = {
  draft: "bg-slate-700 text-slate-100",
  validating: "bg-sky-900 text-sky-100",
  publish_pending: "bg-amber-900 text-amber-100",
  deploying: "bg-amber-800 text-amber-50",
  active: "bg-emerald-800 text-emerald-50",
  paused: "bg-zinc-700 text-zinc-100",
  failed_deployment: "bg-rose-800 text-rose-50",
  archived: "bg-slate-800 text-slate-300",
  success: "bg-emerald-800 text-emerald-50",
  failed: "bg-rose-800 text-rose-50",
  running: "bg-sky-800 text-sky-50",
  queued: "bg-amber-800 text-amber-50",
};

export function StatusBadge({ value }: { value?: string | null }) {
  if (!value) return <span className="text-slate-500">—</span>;
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${COLORS[value] || "bg-slate-700"}`}>
      {value.replaceAll("_", " ")}
    </span>
  );
}
