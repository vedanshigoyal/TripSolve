"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth";

export default function Nav() {
  const { user, ready, logout } = useAuth();
  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          Trip<span className="text-accent">Solve</span>
        </Link>
        <nav className="flex gap-4 text-sm text-muted">
          <Link href="/" className="hover:text-fg">Plan</Link>
          {user && <Link href="/trips" className="hover:text-fg">My trips</Link>}
          <Link href="/compare" className="hover:text-fg">Evaluation</Link>
        </nav>
        <div className="ml-auto flex items-center gap-3 text-sm">
          {!ready ? null : user ? (
            <>
              <span className="text-muted">{user.name}</span>
              <button onClick={logout} className="btn-ghost">Log out</button>
            </>
          ) : (
            <>
              <Link href="/login" className="btn-ghost">Log in</Link>
              <Link href="/register" className="btn-primary">Sign up</Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
