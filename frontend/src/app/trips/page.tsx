"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, TripSummary } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function MyTripsPage() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const [trips, setTrips] = useState<TripSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    api<TripSummary[]>("/trips").then(setTrips).catch((e) => setError(e.message));
  }, [ready, user, router]);

  const remove = async (id: string) => {
    if (!confirm("Delete this trip? Share links will stop working.")) return;
    await api(`/trips/${id}`, { method: "DELETE" });
    setTrips((t) => t?.filter((x) => x.id !== id) ?? null);
  };

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">My trips</h1>
        <Link href="/" className="btn-primary">New trip</Link>
      </div>
      {error && <p className="rounded-lg bg-bad-soft p-2 text-sm text-bad">{error}</p>}
      {trips === null ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : trips.length === 0 ? (
        <div className="card text-sm text-muted">No saved trips yet. Plan one and press <strong>Save trip</strong>.</div>
      ) : (
        <ul className="space-y-2">
          {trips.map((t) => (
            <li key={t.id} className="card flex items-center gap-4">
              <Link href={`/trips/${t.id}`} className="min-w-0 flex-1">
                <div className="font-medium">{t.title}</div>
                <div className="text-xs text-muted">
                  {new Date(t.date + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}
                  {t.days > 1 && ` · ${t.days} days`} · {t.is_group ? `group of ${t.members}` : "solo"}
                  {t.stops !== null && ` · ${t.stops} stops`}
                </div>
              </Link>
              <button className="btn-ghost text-bad" onClick={() => remove(t.id)}>Delete</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
