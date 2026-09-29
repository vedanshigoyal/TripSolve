"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import Workspace from "@/components/Workspace";
import { api, defaultParams, memberBody, Trip } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function PlanPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [group, setGroup] = useState(false);
  const [initialParams] = useState(defaultParams);

  const header = (
    <div className="space-y-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Plan a day in Jaipur</h1>
        <p className="text-sm text-muted">
          Routes are optimised by a solver, not guessed by AI, so every stop fits its opening hours.
        </p>
      </div>
      <div className="inline-flex rounded-lg border border-line p-0.5 text-sm">
        {[false, true].map((g) => (
          <button key={String(g)} onClick={() => setGroup(g)}
            className={`rounded-md px-3 py-1 ${group === g ? "bg-accent text-white" : "text-muted"}`}>
            {g ? "Group trip" : "Solo trip"}
          </button>
        ))}
      </div>
      {!user && (
        <p className="text-xs text-muted">
          Planning as a guest. <Link href="/login" className="text-accent underline">Log in</Link> to save trips and invite your group.
        </p>
      )}
    </div>
  );

  return (
    <Workspace
      initialParams={initialParams}
      initialMembers={[{ name: "You", interests: {}, must_visit: [], avoid: [] }]}
      group={group}
      header={header}
      saveLabel={group ? "Save & invite" : "Save trip"}
      onSave={
        user
          ? async ({ params, members, result }) => {
              const title = prompt("Name this trip", group ? "Group trip to Jaipur" : "Day in Jaipur");
              if (!title) return;
              const trip = await api<Trip>("/trips", {
                body: { title, is_group: group, params, members: members.map(memberBody), result },
              });
              router.push(`/trips/${trip.id}`);
            }
          : undefined
      }
    />
  );
}
