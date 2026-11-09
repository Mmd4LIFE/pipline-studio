"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Shell } from "@/components/shell";
import { StatusBadge } from "@/components/status-badge";
import { api } from "@/lib/api";

export default function JobsPage() {
  const router = useRouter();
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: api.jobs, refetchInterval: 4000 });
  const run = useMutation({
    mutationFn: api.run,
    onSuccess: () => jobs.refetch(),
  });
  const pause = useMutation({
    mutationFn: api.pause,
    onSuccess: () => jobs.refetch(),
  });
  const resume = useMutation({
    mutationFn: api.resume,
    onSuccess: () => jobs.refetch(),
  });

  return (
    <Shell>
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Jobs</h1>
          <p className="text-sm text-slate-400">Declarative SQL pipelines published to Airflow 2.10.5</p>
        </div>
        <Link href="/jobs/new" className="rounded-lg bg-accent px-4 py-2 font-semibold text-ink">
          New job
        </Link>
      </div>
      <div className="overflow-hidden rounded-2xl border border-line bg-panel">
        <table className="w-full text-left text-sm">
          <thead className="bg-white/5 text-slate-400">
            <tr>
              {["Name", "Source", "Destination", "Schedule", "Desired", "Last run", "Rows", "Actions"].map((h) => (
                <th key={h} className="px-4 py-3 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(jobs.data || []).map((job) => (
              <tr key={job.id} className="border-t border-line/80">
                <td className="px-4 py-3">
                  <Link href={`/jobs/${job.id}`} className="font-medium text-white hover:text-accent">
                    {job.name}
                  </Link>
                  <div className="text-xs text-slate-500">{job.dag_id}</div>
                </td>
                <td className="px-4 py-3">{job.source_name}</td>
                <td className="px-4 py-3 font-mono text-xs">{job.destination_label}</td>
                <td className="px-4 py-3 font-mono text-xs">{job.schedule_label}</td>
                <td className="px-4 py-3">
                  <StatusBadge value={job.status} />
                </td>
                <td className="px-4 py-3">
                  <StatusBadge value={job.last_run?.state} />
                </td>
                <td className="px-4 py-3">{job.last_run?.rows_written ?? "—"}</td>
                <td className="px-4 py-3">
                  <div className="flex gap-2 text-xs">
                    <button className="hover:text-accent" onClick={() => run.mutate(job.id)}>
                      Run
                    </button>
                    {job.status === "paused" ? (
                      <button className="hover:text-accent" onClick={() => resume.mutate(job.id)}>
                        Resume
                      </button>
                    ) : (
                      <button className="hover:text-accent" onClick={() => pause.mutate(job.id)}>
                        Pause
                      </button>
                    )}
                    <button className="hover:text-accent" onClick={() => router.push(`/jobs/${job.id}`)}>
                      View
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {jobs.data?.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-slate-400">
                  No jobs yet. Create the Ludo daily user stats pipeline to start.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
