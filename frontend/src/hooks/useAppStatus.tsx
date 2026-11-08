"use client";

import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";

import { api } from "@/services/api";
import type { ProvidersResponse, Subject, UserSettings } from "@/types/api";

interface AppStatus {
  providers: ProvidersResponse | null;
  settings: UserSettings | null;
  subjects: Subject[];
  backendError: string | null;
  refresh: (force?: boolean) => Promise<void>;
  refreshSubjects: () => Promise<void>;
  setSettings: (s: UserSettings) => void;
}

const Ctx = createContext<AppStatus | null>(null);

export function AppStatusProvider({ children }: { children: ReactNode }) {
  const [providers, setProviders] = useState<ProvidersResponse | null>(null);
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [backendError, setBackendError] = useState<string | null>(null);

  const refresh = useCallback(async (force = false) => {
    try {
      const [p, s] = await Promise.all([api.providers(force), api.settings()]);
      setProviders(p);
      setSettings(s);
      setBackendError(null);
    } catch (e) {
      setBackendError((e as Error).message);
    }
  }, []);
  const refreshSubjects = useCallback(async () => {
    try { setSubjects(await api.subjects()); } catch { /* reported via backendError */ }
  }, []);

  useEffect(() => {
    refresh();
    refreshSubjects();
    const id = setInterval(() => refresh(), 60000);
    return () => clearInterval(id);
  }, [refresh, refreshSubjects]);

  return (
    <Ctx.Provider value={{ providers, settings, subjects, backendError, refresh, refreshSubjects, setSettings }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAppStatus(): AppStatus {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAppStatus must be used within AppStatusProvider");
  return v;
}
