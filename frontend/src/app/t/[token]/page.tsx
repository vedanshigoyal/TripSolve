"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import Workspace from "@/components/Workspace";
import { api, Trip } from "@/lib/api";
import { saveTrip } from "@/lib/trips";

/** Share-link view: read-only for the view token, collaborative for the invite (edit) token. */
export default function SharedTripPage() {
  const { token } = useParams<{ token: string }>();
  const [trip, setTrip] = useState<Trip | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Trip>(`/shared/${token}`).then(setTrip).catch((e) => setError(e.message));
  }, [token]);

  if (error) return <p className="mx-auto max-w-xl p-8 text-bad">{error}</p>;
  if (!trip) return <p className="mx-auto max-w-xl p-8 text-muted">Loading trip…</p>;

  const editor = trip.role === "editor";
  return (
    <Workspace
      key={trip.updated_at}
      initialParams={trip.params}
      initialMembers={trip.members.length ? trip.members : [{ name: "You", interests: {}, must_visit: [], avoid: [] }]}
      initialResult={trip.result}
      group={trip.is_group}
      readOnly={!editor}
      saveLabel="Save for everyone"
      header={
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">{trip.title}</h1>
          <p className="text-sm text-muted">
            Planned by {trip.owner_name}.{" "}
            {editor
              ? "Add yourself with “+ member”, pick your interests, re-plan, then save so everyone sees the new route."
              : "This is a read-only link."}
          </p>
        </div>
      }
      onSave={editor ? async (state) => setTrip(await saveTrip(`/shared/${token}`, trip.members, state)) : undefined}
    />
  );
}
