"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, retry: false });

  if (me.isError) {
    router.replace("/login");
    return null;
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-line/80 bg-ink/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-ink font-bold">Σ</div>
            <div>
              <p className="text-sm font-semibold tracking-wide">SQL Pipeline Studio</p>
              <p className="text-xs text-slate-400">PostgreSQL ETL control plane</p>
            </div>
          </div>
          <nav className="flex items-center gap-5 text-sm">
            <Link className={navClass(pathname, "/jobs")} href="/jobs">
              Jobs
            </Link>
            <Link className={navClass(pathname, "/connections")} href="/connections">
              Connections
            </Link>
            <span className="text-slate-500">{me.data?.email}</span>
            <button
              className="rounded-lg border border-line px-3 py-1.5 text-slate-300 hover:bg-white/5"
              onClick={async () => {
                await api.logout();
                router.replace("/login");
              }}
            >
              Sign out
            </button>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">{me.isLoading ? <p>Loading…</p> : children}</main>
    </div>
  );
}

function navClass(pathname: string, href: string) {
  return pathname.startsWith(href) ? "text-accent" : "text-slate-300 hover:text-white";
}
