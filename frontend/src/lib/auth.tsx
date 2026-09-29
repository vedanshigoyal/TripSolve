"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getToken, setToken, User } from "./api";

interface AuthState {
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let me: User | null = null;
      if (getToken()) {
        try {
          me = await api<User>("/auth/me");
        } catch {
          setToken(null);
        }
      }
      if (!cancelled) {
        setUser(me);
        setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const finish = (r: { access_token: string; user: User }) => {
    setToken(r.access_token);
    setUser(r.user);
  };

  const login = useCallback(async (email: string, password: string) => {
    finish(await api("/auth/login", { body: { email, password } }));
  }, []);

  const register = useCallback(async (name: string, email: string, password: string) => {
    finish(await api("/auth/register", { body: { name, email, password } }));
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  return <AuthContext.Provider value={{ user, ready, login, register, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
