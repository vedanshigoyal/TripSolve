"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import ShareLinks from "@/components/ShareLinks";
import Workspace from "@/components/Workspace";
import { api, Trip } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { saveTrip } from "@/lib/trips";

export default function TripPage() {
  const { id } = useParams<{ id: string }>();
  const { ready, user } = useAuth();
  const [trip, setTrip] = useState<Trip | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (ready && user) api<Trip>(`/trips/${id}`).then(setTrip).catch((e) => setError(e.message));
  }, [id, ready, user]);

  if (ready && !user) return <p className="mx-auto max-w-xl p-8 text-bad">Log in to open this trip.</p>;
  if (error) return <p className="mx-auto max-w-xl p-8 text-bad">{error}</p>;
  if (!trip) return <p className="mx-auto max-w-xl p-8 text-muted">Loading trip…</p>;

  return (
    <Workspace
      key={trip.updated_at}
      initialParams={trip.params}
      initialMembers={trip.members}
      initialResult={trip.result}
      group={trip.is_group}
      saveLabel="Save changes"
      header={
        <div className="space-y-3">
          <h1 className="text-2xl font-semibold tracking-tight">{trip.title}</h1>
          {trip.is_group && <ShareLinks viewToken={trip.view_token} editToken={trip.edit_token} />}
          {!trip.is_group && <ShareLinks viewToken={trip.view_token} editToken={null} />}
        </div>
      }
      onSave={async (state) => setTrip(await saveTrip(`/trips/${trip.id}`, trip.members, state))}
    />
  );
}
