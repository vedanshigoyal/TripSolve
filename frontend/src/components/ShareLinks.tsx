"use client";

import { useState } from "react";
import { shareUrl } from "@/lib/trips";

export default function ShareLinks({ viewToken, editToken }: { viewToken: string | null; editToken: string | null }) {
  const [copied, setCopied] = useState<string | null>(null);
  const copy = async (label: string, token: string) => {
    try {
      await navigator.clipboard.writeText(shareUrl(token));
      setCopied(label);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      prompt("Copy this link", shareUrl(token));
    }
  };
  if (!viewToken && !editToken) return null;
  return (
    <div className="card space-y-2 text-sm">
      <span className="label">Share</span>
      {editToken && (
        <div className="flex items-center justify-between gap-2">
          <span>Invite link — members add their preferences</span>
          <button className="btn-ghost" onClick={() => copy("edit", editToken)}>{copied === "edit" ? "Copied ✓" : "Copy"}</button>
        </div>
      )}
      {viewToken && (
        <div className="flex items-center justify-between gap-2">
          <span>Read-only link</span>
          <button className="btn-ghost" onClick={() => copy("view", viewToken)}>{copied === "view" ? "Copied ✓" : "Copy"}</button>
        </div>
      )}
    </div>
  );
}
