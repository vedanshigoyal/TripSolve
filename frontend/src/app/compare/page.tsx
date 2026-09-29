"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface Scenario {
  name: string;
  description: string;
}

interface MethodMetrics {
  stops: number;
  total_travel_minutes: number;
  time_window_violations: number;
  requested_included: number;
  requested_total: number;
  total_utility: number;
  runtime_ms: number;
  note: string;
}

interface CompareResult {
  scenario: string;
  candidates: number;
  travel_time_source: string;
  results: Record<"toptw" | "naive" | "llm", MethodMetrics | null>;
}

const METHODS = [
  { key: "toptw", label: "TripSolve (OR-Tools)" },
  { key: "naive", label: "Naive manual plan" },
  { key: "llm", label: "Pure LLM" },
] as const;

export default function ComparePage() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [results, setResults] = useState<Record<string, CompareResult>>({});
  const [running, setRunning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Scenario[]>("/eval/scenarios").then(setScenarios).catch((e) => setError(e.message));
  }, []);

  const runOne = async (name: string) => {
    setRunning(name);
    try {
      const r = await api<CompareResult>(`/eval/scenarios/${name}/run`, { method: "POST" });
      setResults((prev) => ({ ...prev, [name]: r }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(null);
    }
  };

  const runAll = async () => {
    setError(null);
    for (const s of scenarios) await runOne(s.name);
  };

  const totals = METHODS.map(({ key }) => {
    const rs = Object.values(results).map((r) => r.results[key]).filter(Boolean) as MethodMetrics[];
    return {
      key,
      n: rs.length,
      violations: rs.reduce((a, r) => a + r.time_window_violations, 0),
      travel: rs.reduce((a, r) => a + r.total_travel_minutes, 0),
      requested: rs.reduce((a, r) => a + r.requested_included, 0),
      requestedTotal: rs.reduce((a, r) => a + r.requested_total, 0),
    };
  });

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Evaluation: solver vs baselines</h1>
          <p className="max-w-2xl text-sm text-muted">
            Each scenario is planned three ways over the same places and road travel times, then every plan is executed by
            the same simulator. A violation means arriving when a place is closed or too late to finish the visit, or
            overrunning the day.
          </p>
        </div>
        <button className="btn-primary" disabled={!!running || !scenarios.length} onClick={runAll}>
          {running ? `Running ${running}…` : "Run all scenarios"}
        </button>
      </div>
      {error && <p className="mb-4 rounded-lg bg-bad-soft p-2 text-sm text-bad">{error}</p>}

      {Object.keys(results).length > 0 && (
        <div className="mb-6 grid gap-3 sm:grid-cols-3">
          {totals.map((t) => (
            <div key={t.key} className="card">
              <div className="text-xs uppercase tracking-wide text-muted">{METHODS.find((m) => m.key === t.key)?.label}</div>
              {t.n === 0 ? (
                <div className="mt-1 text-sm text-muted">Not run (needs GROQ_API_KEY)</div>
              ) : (
                <>
                  <div className={`mt-1 text-3xl font-semibold ${t.violations ? "text-bad" : "text-ok"}`}>{t.violations}</div>
                  <div className="text-xs text-muted">violations · {t.travel} min travel · {t.requested}/{t.requestedTotal} requested stops</div>
                </>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="p-3">Scenario</th>
              <th className="p-3">Method</th>
              <th className="p-3 text-right">Stops</th>
              <th className="p-3 text-right">Travel</th>
              <th className="p-3 text-right">Violations</th>
              <th className="p-3 text-right">Requested</th>
              <th className="p-3 text-right">Utility</th>
            </tr>
          </thead>
          <tbody>
            {scenarios.map((s) => {
              const r = results[s.name];
              return METHODS.map((m, i) => {
                const x = r?.results[m.key];
                return (
                  <tr key={s.name + m.key} className={i === METHODS.length - 1 ? "border-b border-line" : ""}>
                    {i === 0 && (
                      <td rowSpan={METHODS.length} className="p-3 align-top">
                        <div className="font-medium">{s.name}</div>
                        <div className="text-xs text-muted">{s.description}</div>
                        <button className="btn-ghost mt-2 text-xs" disabled={!!running} onClick={() => runOne(s.name)}>
                          {running === s.name ? "Running…" : r ? "Re-run" : "Run"}
                        </button>
                      </td>
                    )}
                    <td className="p-3">{m.label}</td>
                    {x ? (
                      <>
                        <td className="p-3 text-right">{x.stops}</td>
                        <td className="p-3 text-right">{x.total_travel_minutes} min</td>
                        <td className={`p-3 text-right font-semibold ${x.time_window_violations ? "text-bad" : "text-ok"}`}>
                          {x.time_window_violations}
                        </td>
                        <td className="p-3 text-right">{x.requested_included}/{x.requested_total}</td>
                        <td className="p-3 text-right">{x.total_utility}</td>
                      </>
                    ) : (
                      <td colSpan={5} className="p-3 text-right text-xs text-muted">
                        {r ? (m.key === "llm" ? "LLM not configured" : "—") : ""}
                      </td>
                    )}
                  </tr>
                );
              });
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
