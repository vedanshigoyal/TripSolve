"use client";

import type { Member, Poi } from "@/lib/api";

const LEVELS = [
  { value: 0, label: "" },
  { value: 3, label: "like" },
  { value: 5, label: "love" },
];

function nextLevel(v: number | undefined) {
  const i = LEVELS.findIndex((l) => l.value === (v ?? 0));
  return LEVELS[(i + 1) % LEVELS.length].value;
}

interface Props {
  member: Member;
  categories: string[];
  pois: Poi[];
  readOnly?: boolean;
  onChange: (m: Member) => void;
}

export default function PreferencesEditor({ member, categories, pois, readOnly, onChange }: Props) {
  const byId = new Map(pois.map((p) => [p.id, p]));

  const toggleInterest = (c: string) => {
    const interests = { ...member.interests };
    const v = nextLevel(interests[c]);
    if (v === 0) delete interests[c];
    else interests[c] = v;
    onChange({ ...member, interests });
  };

  const addTo = (key: "must_visit" | "avoid", id: number) => {
    const other = key === "must_visit" ? "avoid" : "must_visit";
    onChange({
      ...member,
      [key]: [...new Set([...member[key], id])],
      [other]: member[other].filter((x) => x !== id),
    });
  };

  const removeFrom = (key: "must_visit" | "avoid", id: number) =>
    onChange({ ...member, [key]: member[key].filter((x) => x !== id) });

  const available = pois.filter((p) => !member.must_visit.includes(p.id) && !member.avoid.includes(p.id));

  return (
    <div className="space-y-4">
      <div>
        <span className="label">Interests — tap to cycle: like → love → off</span>
        <div className="flex flex-wrap gap-1.5">
          {categories.map((c) => {
            const v = member.interests[c] ?? 0;
            const style =
              v >= 5 ? "border-accent bg-accent text-white" : v > 0 ? "border-accent bg-accent-soft text-accent" : "text-muted";
            return (
              <button
                key={c}
                type="button"
                disabled={readOnly}
                onClick={() => toggleInterest(c)}
                className={`chip capitalize transition ${style}`}
              >
                {c}
                {v > 0 && <span className="ml-1 opacity-80">· {LEVELS.find((l) => l.value === v)?.label ?? v}</span>}
              </button>
            );
          })}
        </div>
      </div>

      {(["must_visit", "avoid"] as const).map((key) => (
        <div key={key}>
          <span className="label">{key === "must_visit" ? "Must visit" : "Avoid"}</span>
          <div className="flex flex-wrap items-center gap-1.5">
            {member[key].map((id) => (
              <span
                key={id}
                className={`chip flex items-center gap-1 ${key === "must_visit" ? "border-ok bg-ok-soft" : "border-bad bg-bad-soft"}`}
              >
                {byId.get(id)?.name ?? `#${id}`}
                {!readOnly && (
                  <button type="button" aria-label="remove" onClick={() => removeFrom(key, id)} className="opacity-60 hover:opacity-100">
                    ✕
                  </button>
                )}
              </span>
            ))}
            {!readOnly && (
              <select
                className="input w-auto py-1 text-xs"
                value=""
                onChange={(e) => e.target.value && addTo(key, Number(e.target.value))}
              >
                <option value="">+ add place…</option>
                {available.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
