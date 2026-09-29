export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Strategy = "fair" | "average" | "least_misery";

export interface Poi {
  id: number;
  slug: string;
  name: string;
  description: string;
  lat: number;
  lon: number;
  categories: string[];
  visit_minutes: number;
  popularity: number;
  opening_hours: Record<string, [string, string][]>;
  entry_fee_inr: number | null;
}

export interface LatLon {
  lat: number;
  lon: number;
  label: string;
}

export interface Member {
  id?: number;
  name: string;
  interests: Record<string, number>;
  must_visit: number[];
  avoid: number[];
}

export interface TripParams {
  city: string;
  date: string;
  days: number;
  start_time: string;
  end_time: string;
  start_location: LatLon;
  return_to_start: boolean;
  strategy: Strategy;
  radius_km: number;
  exclude: number[];
  include: number[];
}

export interface Stop {
  poi: Poi;
  arrival: string;
  start: string;
  end: string;
  wait_minutes: number;
  travel_minutes: number;
  utility: number;
  violation: string | null;
}

export interface Day {
  day: number;
  date: string;
  start: string;
  end: string;
  travel_minutes: number;
  return_travel_minutes: number;
  stops: Stop[];
  geometry: [number, number][];
  violations: string[];
}

export interface PlanResponse {
  feasible: boolean;
  days: Day[];
  skipped: { poi_id: number; name: string; utility: number; reason: string }[];
  metrics: {
    stops: number;
    total_travel_minutes: number;
    total_utility: number;
    time_window_violations: number;
    solve_ms: number;
    candidates: number;
    travel_time_source: "osrm" | "cache" | "estimate";
    must_visit_missed: number;
  };
  member_satisfaction: Record<string, number> | null;
  explanation: string | null;
  explanation_source: "llm" | "template" | null;
}

export interface ParseResult {
  ok: boolean;
  used_llm: boolean;
  interests: Record<string, number>;
  must_visit: number[];
  avoid: number[];
  start_time: string | null;
  end_time: string | null;
  days: number | null;
  message: string;
}

export interface User {
  id: number;
  email: string;
  name: string;
}

export interface Trip {
  id: string;
  title: string;
  is_group: boolean;
  city: string;
  params: TripParams;
  members: Member[];
  result: PlanResponse | null;
  owner_name: string;
  role: "owner" | "editor" | "viewer";
  view_token: string | null;
  edit_token: string | null;
  created_at: string;
  updated_at: string;
}

export interface TripSummary {
  id: string;
  title: string;
  is_group: boolean;
  date: string;
  days: number;
  members: number;
  stops: number | null;
  updated_at: string;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const TOKEN_KEY = "tripsolve_token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: session-only login */
  }
}

function detailMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ");
  }
  return `Request failed (${status})`;
}

export async function api<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: init.method ?? (init.body ? "POST" : "GET"),
      headers,
      body: init.body ? JSON.stringify(init.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Can't reach the TripSolve server. Is the backend running?");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, detailMessage(body, res.status));
  return body as T;
}

export const START_PRESETS: LatLon[] = [
  { lat: 26.9196, lon: 75.7878, label: "Jaipur Junction (railway station)" },
  { lat: 26.8242, lon: 75.8122, label: "Jaipur International Airport" },
  { lat: 26.9239, lon: 75.8267, label: "Hawa Mahal / Old City" },
  { lat: 26.9061, lon: 75.8062, label: "MI Road / C-Scheme hotels" },
];

export function todayIso(): string {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

export function defaultParams(): TripParams {
  return {
    city: "jaipur",
    date: todayIso(),
    days: 1,
    start_time: "09:00",
    end_time: "18:00",
    start_location: START_PRESETS[0],
    return_to_start: true,
    strategy: "fair",
    radius_km: 40,
    exclude: [],
    include: [],
  };
}

/** Member as the API expects it in request bodies (without the DB id). */
export function memberBody({ name, interests, must_visit, avoid }: Member) {
  return { name, interests, must_visit, avoid };
}
