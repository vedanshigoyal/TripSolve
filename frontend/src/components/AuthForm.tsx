"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/auth";

export default function AuthForm({ mode }: { mode: "login" | "register" }) {
  const { login, register } = useAuth();
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(email, password);
      else await register(name, email, password);
      router.push("/trips");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-sm px-4 py-12">
      <form onSubmit={submit} className="card space-y-4">
        <h1 className="text-xl font-semibold">{mode === "login" ? "Log in" : "Create an account"}</h1>
        {mode === "register" && (
          <label className="block">
            <span className="label">Name</span>
            <input className="input" required value={name} onChange={(e) => setName(e.target.value)} />
          </label>
        )}
        <label className="block">
          <span className="label">Email</span>
          <input className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="block">
          <span className="label">Password</span>
          <input className="input" type="password" required minLength={mode === "register" ? 8 : 1}
            value={password} onChange={(e) => setPassword(e.target.value)} />
          {mode === "register" && <span className="mt-1 block text-xs text-muted">At least 8 characters.</span>}
        </label>
        {error && <p className="rounded-lg bg-bad-soft p-2 text-sm text-bad">{error}</p>}
        <button className="btn-primary w-full" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Log in" : "Sign up"}</button>
        <p className="text-center text-sm text-muted">
          {mode === "login" ? (
            <>No account? <Link className="text-accent underline" href="/register">Sign up</Link></>
          ) : (
            <>Have an account? <Link className="text-accent underline" href="/login">Log in</Link></>
          )}
        </p>
      </form>
    </div>
  );
}
