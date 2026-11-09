"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@localhost");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.login(email, password);
      router.replace("/jobs");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={onSubmit} className="w-full max-w-md rounded-2xl border border-line bg-panel p-8 shadow-2xl">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-ink font-bold">Σ</div>
          <div>
            <h1 className="text-xl font-semibold">SQL Pipeline Studio</h1>
            <p className="text-sm text-slate-400">Sign in to manage warehouse jobs</p>
          </div>
        </div>
        <label className="mb-3 block text-sm">
          Email
          <input
            className="mt-1 w-full rounded-lg border border-line bg-ink px-3 py-2"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="mb-4 block text-sm">
          Password
          <input
            type="password"
            className="mt-1 w-full rounded-lg border border-line bg-ink px-3 py-2"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error ? <p className="mb-3 text-sm text-rose-300">{error}</p> : null}
        <button
          disabled={busy}
          className="w-full rounded-lg bg-accent py-2.5 font-semibold text-ink disabled:opacity-60"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
