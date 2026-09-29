"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError, Member, memberBody, ParseResult, PlanResponse, Poi, START_PRESETS, TripParams } from "@/lib/api";
import Itinerary from "./Itinerary";
import PreferencesEditor from "./PreferencesEditor";

// Leaflet touches `window`, so the map only renders in the browser.
const RouteMap = dynamic(() => import("./RouteMap"), {
  ssr: false,
  loading: () => <div className="flex h-full items-center justify-center rounded-xl bg-surface text-sm text-muted">Loading map…</div>,
});

export interface WorkspaceProps {
  initialParams: TripParams;
  initialMembers: Member[];
  initialResult?: PlanResponse | null;
  readOnly?: boolean;
  /** Group mode shows the member tabs and the fairness strategy. */
  group?: boolean;
  /** Lets the members list be edited (add/remove people). */
  canManageMembers?: boolean;
  header?: React.ReactNode;
  saveLabel?: string;
  onSave?: (state: { params: TripParams; members: Member[]; result: PlanResponse | null }) => Promise<void>;
}

const STRATEGY_HELP: Record<TripParams["strategy"], string> = {
  fair: "Balanced: half average happiness, half the least-happy person",
  average: "Maximise the group's average interest",
  least_misery: "Never pick places someone dislikes",
};

export default function Workspace(props: WorkspaceProps) {
  const { readOnly, group, canManageMembers = true, onSave, header, saveLabel = "Save trip" } = props;
  const [params, setParams] = useState<TripParams>(props.initialParams);
  const [members, setMembers] = useState<Member[]>(props.initialMembers);
  const [active, setActive] = useState(0);
  const [result, setResult] = useState<PlanResponse | null>(props.initialResult ?? null);
  const [edited, setEdited] = useState(false);
  const [pois, setPois] = useState<Poi[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [freeText, setFreeText] = useState("");

  useEffect(() => {
    Promise.all([api<Poi[]>(`/cities/${params.city}/pois`), api<string[]>(`/cities/${params.city}/categories`)])
      .then(([p, c]) => {
        setPois(p);
        setCategories(c);
      })
      .catch((e) => setError(e.message));
  }, [params.city]);

  const member = members[Math.min(active, members.length - 1)];
  const mustVisit = useMemo(() => new Set([...members.flatMap((m) => m.must_visit), ...params.include]), [members, params.include]);

  const run = async <T,>(label: string, fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(label);
    setError(null);
    setNotice(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const planBody = (p: TripParams) => ({ ...p, members: members.map(memberBody) });

  const plan = (p: TripParams = params) =>
    run("Optimising route…", async () => {
      setResult(await api<PlanResponse>("/plan", { body: planBody(p) }));
      setEdited(false);
    });

  const checkRoute = (route: number[][], p: TripParams = params) =>
    run("Checking feasibility…", async () => {
      setResult(await api<PlanResponse>("/plan/check", { body: { ...planBody(p), route } }));
      setEdited(true);
    });

  const removeStop = (poiId: number) => {
    if (!result) return;
    const p = { ...params, exclude: [...new Set([...params.exclude, poiId])], include: params.include.filter((x) => x !== poiId) };
    setParams(p);
    checkRoute(result.days.map((d) => d.stops.map((s) => s.poi.id).filter((id) => id !== poiId)), p);
  };

  const reoptimize = () => {
    if (!result) return;
    const kept = result.days.flatMap((d) => d.stops.map((s) => s.poi.id));
    const p = { ...params, include: kept };
    setParams(p);
    plan(p);
  };

  const resetEdits = () => {
    const p = { ...params, include: [], exclude: [] };
    setParams(p);
    plan(p);
  };

  const parseText = () =>
    run("Reading your description…", async () => {
      const r = await api<ParseResult>("/plan/parse", { body: { text: freeText, city: params.city } });
      if (!r.ok) {
        setNotice(r.message || "Couldn't understand that — please use the options below.");
        return;
      }
      setMembers((ms) =>
        ms.map((m, i) =>
          i === active
            ? {
                ...m,
                interests: { ...m.interests, ...r.interests },
                must_visit: [...new Set([...m.must_visit, ...r.must_visit])],
                avoid: [...new Set([...m.avoid, ...r.avoid])],
              }
            : m,
        ),
      );
      setParams((p) => ({
        ...p,
        start_time: r.start_time ?? p.start_time,
        end_time: r.end_time ?? p.end_time,
        days: r.days ?? p.days,
      }));
      setNotice(`${r.used_llm ? "AI" : "Keyword matching"} filled in the form below — check it, then plan.`);
    });

  const save = () =>
    onSave && run("Saving…", async () => {
      await onSave({ params, members, result });
      setNotice("Saved.");
    });

  const updateMember = (m: Member) => setMembers((ms) => ms.map((x, i) => (i === active ? m : x)));

  const addMember = () => {
    const name = prompt("Member name")?.trim();
    if (!name) return;
    if (members.some((m) => m.name === name)) return setError("Member names must be unique");
    setMembers((ms) => [...ms, { name, interests: {}, must_visit: [], avoid: [] }]);
    setActive(members.length);
  };

  const removeMember = (i: number) => {
    if (members.length <= 1) return;
    setMembers((ms) => ms.filter((_, j) => j !== i));
    setActive(0);
  };

  const setStart = (lat: number, lon: number) =>
    setParams((p) => ({ ...p, start_location: { lat, lon, label: "Custom start (map)" } }));

  const presetIndex = START_PRESETS.findIndex(
    (s) => s.lat === params.start_location.lat && s.lon === params.start_location.lon,
  );

  return (
    <div className="mx-auto grid max-w-7xl gap-4 px-4 py-4 lg:grid-cols-[380px_1fr]">
      {/* ---------- left: inputs ---------- */}
      <section className="space-y-4">
        {header}

        {!readOnly && (
          <div className="card space-y-2">
            <span className="label">Describe your trip (optional)</span>
            <textarea
              className="input min-h-20 resize-y"
              placeholder="e.g. We have from 10am to 7pm, love forts and street food, and must see Hawa Mahal. Not into shopping."
              value={freeText}
              onChange={(e) => setFreeText(e.target.value)}
            />
            <button className="btn-ghost" disabled={!!busy || freeText.trim().length < 3} onClick={parseText}>
              ✨ Fill form from text
            </button>
          </div>
        )}

        <div className="card space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <label>
              <span className="label">Date</span>
              <input type="date" className="input" disabled={readOnly} value={params.date}
                onChange={(e) => setParams({ ...params, date: e.target.value })} />
            </label>
            <label>
              <span className="label">Days</span>
              <select className="input" disabled={readOnly} value={params.days}
                onChange={(e) => setParams({ ...params, days: Number(e.target.value) })}>
                {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <label>
              <span className="label">Start</span>
              <input type="time" className="input" disabled={readOnly} value={params.start_time}
                onChange={(e) => setParams({ ...params, start_time: e.target.value })} />
            </label>
            <label>
              <span className="label">End</span>
              <input type="time" className="input" disabled={readOnly} value={params.end_time}
                onChange={(e) => setParams({ ...params, end_time: e.target.value })} />
            </label>
          </div>
          <label className="block">
            <span className="label">Starting point</span>
            <select className="input" disabled={readOnly} value={presetIndex}
              onChange={(e) => {
                const i = Number(e.target.value);
                if (i >= 0) setParams({ ...params, start_location: START_PRESETS[i] });
              }}>
              {presetIndex < 0 && <option value={-1}>{params.start_location.label}</option>}
              {START_PRESETS.map((s, i) => <option key={s.label} value={i}>{s.label}</option>)}
            </select>
            {!readOnly && <span className="mt-1 block text-xs text-muted">Or click the map / drag the 📍 pin.</span>}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" disabled={readOnly} checked={params.return_to_start}
              onChange={(e) => setParams({ ...params, return_to_start: e.target.checked })} />
            Return to the starting point each day
          </label>
          {group && (
            <label className="block">
              <span className="label">Group fairness</span>
              <select className="input" disabled={readOnly} value={params.strategy}
                onChange={(e) => setParams({ ...params, strategy: e.target.value as TripParams["strategy"] })}>
                <option value="fair">Fair (recommended)</option>
                <option value="average">Average</option>
                <option value="least_misery">Least misery</option>
              </select>
              <span className="mt-1 block text-xs text-muted">{STRATEGY_HELP[params.strategy]}</span>
            </label>
          )}
        </div>

        <div className="card space-y-3">
          {group && (
            <div className="flex flex-wrap items-center gap-1.5">
              {members.map((m, i) => (
                <button key={m.name} onClick={() => setActive(i)}
                  className={`chip ${i === active ? "border-accent bg-accent-soft text-accent" : ""}`}>
                  {m.name}
                  {canManageMembers && !readOnly && members.length > 1 && i === active && (
                    <span role="button" className="ml-1 opacity-60 hover:opacity-100" onClick={(e) => { e.stopPropagation(); removeMember(i); }}>✕</span>
                  )}
                </button>
              ))}
              {canManageMembers && !readOnly && <button className="chip text-muted" onClick={addMember}>+ member</button>}
            </div>
          )}
          {member && (
            <PreferencesEditor member={member} categories={categories} pois={pois} readOnly={readOnly} onChange={updateMember} />
          )}
        </div>

        {!readOnly && (
          <div className="flex flex-wrap gap-2">
            <button className="btn-primary flex-1" disabled={!!busy} onClick={() => plan()}>
              {busy === "Optimising route…" ? "Optimising…" : result ? "Re-plan from scratch" : "Plan my trip"}
            </button>
            {onSave && <button className="btn-ghost" disabled={!!busy} onClick={save}>{saveLabel}</button>}
          </div>
        )}
        {busy && <p className="text-sm text-muted">{busy}</p>}
        {error && <p className="rounded-lg bg-bad-soft p-2 text-sm text-bad">{error}</p>}
        {notice && <p className="rounded-lg bg-ok-soft p-2 text-sm text-ok">{notice}</p>}
      </section>

      {/* ---------- right: map + results ---------- */}
      <section className="space-y-4">
        <div className="h-[420px] lg:h-[480px]">
          <RouteMap
            pois={pois}
            days={result?.days ?? []}
            start={params.start_location}
            mustVisit={mustVisit}
            onStartChange={readOnly ? undefined : setStart}
          />
        </div>

        {result ? (
          <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
            <div className="card">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className={`chip font-medium ${result.feasible ? "border-ok bg-ok-soft text-ok" : "border-bad bg-bad-soft text-bad"}`}>
                  {result.feasible ? "✓ All opening hours respected" : `⚠ ${result.metrics.time_window_violations} timing problem(s)`}
                </span>
                {edited && <span className="chip text-muted">Edited by you</span>}
                {!readOnly && (
                  <span className="ml-auto flex gap-2">
                    {edited && <button className="btn-ghost" disabled={!!busy} onClick={reoptimize} title="Keep your stops, let the solver fix order and fill gaps">Re-optimise</button>}
                    {(params.exclude.length > 0 || params.include.length > 0) && (
                      <button className="btn-ghost" disabled={!!busy} onClick={resetEdits}>Reset edits</button>
                    )}
                  </span>
                )}
              </div>
              {!readOnly && <p className="mb-3 text-xs text-muted">Drag stops to reorder (even across days) or ✕ to remove — we&apos;ll re-check the timings.</p>}
              <Itinerary result={result} editable={!readOnly && !busy} onReorder={(r) => checkRoute(r)} onRemove={removeStop} />
            </div>

            <div className="space-y-4">
              <div className="card">
                <h3 className="mb-2 font-semibold">Why this route?</h3>
                <p className="whitespace-pre-line text-sm leading-relaxed">
                  {result.explanation ?? "Explanations are generated when the solver plans the route."}
                </p>
                {result.explanation_source && (
                  <p className="mt-2 text-xs text-muted">
                    {result.explanation_source === "llm" ? "Written by AI from the solver's facts." : "Generated from the solver's facts."} The route itself is always computed by the optimiser.
                  </p>
                )}
              </div>

              {result.member_satisfaction && (
                <div className="card">
                  <h3 className="mb-2 font-semibold">How fair is it?</h3>
                  <p className="mb-3 text-xs text-muted">Share of each person&apos;s top picks this route covers.</p>
                  {Object.entries(result.member_satisfaction).map(([name, v]) => (
                    <div key={name} className="mb-2">
                      <div className="flex justify-between text-xs"><span>{name}</span><span>{Math.round(v * 100)}%</span></div>
                      <div className="h-2 rounded bg-bg"><div className="h-2 rounded bg-accent" style={{ width: `${Math.round(v * 100)}%` }} /></div>
                    </div>
                  ))}
                </div>
              )}

              <div className="card text-sm">
                <h3 className="mb-2 font-semibold">Numbers</h3>
                <dl className="grid grid-cols-2 gap-y-1">
                  <dt className="text-muted">Stops</dt><dd>{result.metrics.stops}</dd>
                  <dt className="text-muted">Travel</dt><dd>{result.metrics.total_travel_minutes} min</dd>
                  <dt className="text-muted">Candidates</dt><dd>{result.metrics.candidates}</dd>
                  <dt className="text-muted">Solve time</dt><dd>{result.metrics.solve_ms} ms</dd>
                  <dt className="text-muted">Travel times</dt>
                  <dd>{result.metrics.travel_time_source === "estimate" ? "estimated ⚠" : "OSRM road network"}</dd>
                </dl>
              </div>

              {result.skipped.length > 0 && (
                <details className="card text-sm">
                  <summary className="cursor-pointer font-semibold">Skipped places ({result.skipped.length})</summary>
                  <ul className="mt-2 space-y-1.5">
                    {result.skipped.map((s) => (
                      <li key={s.poi_id}><span className="font-medium">{s.name}</span> <span className="text-muted">— {s.reason}</span></li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          </div>
        ) : (
          <div className="card text-sm text-muted">
            Pick a time window and a few interests, then press <strong>Plan my trip</strong>. TripSolve chooses and orders the
            places with an optimisation solver so every stop fits its opening hours.
          </div>
        )}
      </section>
    </div>
  );
}
