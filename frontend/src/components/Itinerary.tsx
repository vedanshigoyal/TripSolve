"use client";

import { useState } from "react";
import type { PlanResponse } from "@/lib/api";
import { DAY_COLORS } from "@/lib/colors";

interface Props {
  result: PlanResponse;
  editable: boolean;
  onReorder: (route: number[][]) => void;
  onRemove: (poiId: number) => void;
}

type DragRef = { day: number; index: number };

function fmtDate(iso: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

export default function Itinerary({ result, editable, onReorder, onRemove }: Props) {
  const [drag, setDrag] = useState<DragRef | null>(null);
  const [over, setOver] = useState<DragRef | null>(null);
  const route = result.days.map((d) => d.stops.map((s) => s.poi.id));

  const drop = (target: DragRef) => {
    if (!drag) return;
    const next = route.map((d) => [...d]);
    const [moved] = next[drag.day].splice(drag.index, 1);
    let idx = target.index;
    if (drag.day === target.day && drag.index < target.index) idx -= 1;
    next[target.day].splice(idx, 0, moved);
    setDrag(null);
    setOver(null);
    if (JSON.stringify(next) !== JSON.stringify(route)) onReorder(next);
  };

  const dropProps = (target: DragRef) =>
    editable
      ? {
          onDragOver: (e: React.DragEvent) => {
            e.preventDefault();
            setOver(target);
          },
          onDrop: (e: React.DragEvent) => {
            e.preventDefault();
            drop(target);
          },
        }
      : {};

  return (
    <div className="space-y-4">
      {result.days.map((d) => {
        const color = DAY_COLORS[d.day % DAY_COLORS.length];
        return (
          <div key={d.day}>
            <div className="mb-2 flex items-baseline justify-between">
              <h3 className="font-semibold" style={{ color }}>
                {result.days.length > 1 ? `Day ${d.day + 1} · ` : ""}
                {fmtDate(d.date)}
              </h3>
              <span className="text-xs text-muted">
                {d.start}–{d.end} · {d.travel_minutes} min travel
              </span>
            </div>
            {d.stops.length === 0 && (
              <div {...dropProps({ day: d.day, index: 0 })} className="rounded-lg border border-dashed border-line p-3 text-sm text-muted">
                No stops this day{editable ? " — drag one here" : ""}.
              </div>
            )}
            <ol className="space-y-1.5">
              {d.stops.map((s, i) => {
                const isOver = over?.day === d.day && over.index === i && drag !== null;
                return (
                  <li
                    key={s.poi.id}
                    draggable={editable}
                    onDragStart={() => setDrag({ day: d.day, index: i })}
                    onDragEnd={() => {
                      setDrag(null);
                      setOver(null);
                    }}
                    {...dropProps({ day: d.day, index: i })}
                    className={`group flex gap-3 rounded-lg border p-2.5 text-sm transition ${
                      s.violation ? "border-bad bg-bad-soft" : "border-line bg-surface"
                    } ${editable ? "cursor-grab active:cursor-grabbing" : ""} ${isOver ? "border-t-4 border-t-accent" : ""}`}
                  >
                    <div
                      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
                      style={{ background: color }}
                    >
                      {i + 1}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <span className="font-medium">{s.poi.name}</span>
                        <span className="shrink-0 font-mono text-xs">
                          {s.start}–{s.end}
                        </span>
                      </div>
                      <div className="mt-0.5 text-xs text-muted">
                        {s.travel_minutes} min travel
                        {s.wait_minutes > 0 && ` · wait ${s.wait_minutes} min (opens ${s.start})`}
                        {s.poi.entry_fee_inr ? ` · ₹${s.poi.entry_fee_inr}` : ""}
                      </div>
                      {s.violation && <div className="mt-1 text-xs font-medium text-bad">⚠ {s.violation}</div>}
                    </div>
                    {editable && (
                      <button
                        type="button"
                        onClick={() => onRemove(s.poi.id)}
                        className="self-start text-muted opacity-0 transition group-hover:opacity-100 hover:text-bad"
                        aria-label={`Remove ${s.poi.name}`}
                        title="Remove from route"
                      >
                        ✕
                      </button>
                    )}
                  </li>
                );
              })}
              {editable && d.stops.length > 0 && (
                <li {...dropProps({ day: d.day, index: d.stops.length })} className="h-3" aria-hidden />
              )}
            </ol>
            {d.return_travel_minutes > 0 && (
              <div className="mt-1.5 text-xs text-muted">↩ {d.return_travel_minutes} min back to start</div>
            )}
            {d.violations.map((v) => (
              <div key={v} className="mt-1 text-xs font-medium text-bad">
                ⚠ {v}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}
