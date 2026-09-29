import { api, Member, memberBody, PlanResponse, Trip, TripParams } from "./api";

/** Persist workspace state to a saved trip, via owner (`/trips/{id}`) or share-link (`/shared/{token}`) routes. */
export async function saveTrip(
  base: string,
  original: Member[],
  state: { params: TripParams; members: Member[]; result: PlanResponse | null },
): Promise<Trip> {
  const keep = new Set(state.members.map((m) => m.name));
  for (const m of original) {
    if (m.id !== undefined && !keep.has(m.name)) await api(`${base}/members/${m.id}`, { method: "DELETE" });
  }
  for (const m of state.members.map(memberBody)) {
    await api(`${base}/members`, { method: "PUT", body: m });
  }
  return api<Trip>(base, { method: "PATCH", body: { params: state.params, result: state.result } });
}

export function shareUrl(token: string) {
  return `${window.location.origin}/t/${token}`;
}
