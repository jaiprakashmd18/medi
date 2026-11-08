"use client";

import {
  BookMarked, Bot, ChartLine, ClipboardCheck, Cloud, Cpu, GraduationCap, Image as ImageIcon, LayoutDashboard,
  Library, Menu, Repeat, Settings, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";

import { Alert } from "@/components/ui";
import { AppStatusProvider, useAppStatus } from "@/hooks/useAppStatus";
import { cn } from "@/lib/utils";
import { api, getToken } from "@/services/api";

export const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/library", label: "My Library", icon: Library },
  { href: "/subjects", label: "Subjects", icon: BookMarked },
  { href: "/tutor", label: "AI Medical Tutor", icon: Bot },
  { href: "/visual", label: "Visual Learning", icon: ImageIcon },
  { href: "/practice", label: "Practice & Exams", icon: ClipboardCheck },
  { href: "/revision", label: "Revision Centre", icon: Repeat },
  { href: "/progress", label: "Progress Analytics", icon: ChartLine },
  { href: "/settings", label: "Settings", icon: Settings },
];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2.5 px-2">
      <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-cyan-400 to-teal-400 text-navy-950 shadow-glow">
        <GraduationCap className="h-5 w-5" />
      </div>
      <div className="leading-tight">
        <div className="text-[15px] font-bold tracking-wide text-white">MEDI-GENIUS</div>
        <div className="text-[10px] uppercase tracking-[0.2em] text-accent/80">Medical AI tutor</div>
      </div>
    </Link>
  );
}

function AIStatusPill() {
  const { providers, settings, backendError } = useAppStatus();
  if (backendError) return <span className="chip border-rose-400/30 bg-rose-400/10 text-rose-300">Backend offline</span>;
  if (!providers) return <span className="chip border-white/10 text-ink-faint">Checking AI…</span>;
  const route = providers.routes.explain;
  const mode = { auto: "Auto", local_only: "Local only", cloud_only: "Cloud only" }[settings?.ai_mode ?? "auto"];
  if (!route?.ok)
    return (
      <Link href="/settings" title={route?.reason} className="chip border-amber-400/30 bg-amber-400/10 text-amber-300">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-300" /> No AI provider · {mode}
      </Link>
    );
  const Icon = route.provider === "anthropic" ? Cloud : Cpu;
  return (
    <Link href="/settings" title={route.reason} className="chip border-accent/30 bg-accent/10 text-accent-soft">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
      <Icon className="h-3 w-3" /> {route.provider === "anthropic" ? "Claude" : "Ollama"} · {route.model} · {mode}
    </Link>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="flex h-full flex-col gap-1">
      <div className="mb-6 mt-1"><Logo /></div>
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = isActive(pathname, href);
        return (
          <Link key={href} href={href} onClick={onNavigate} aria-current={active ? "page" : undefined}
            className={cn("focus-ring group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition",
              active ? "bg-gradient-to-r from-accent/15 to-transparent text-white shadow-[inset_2px_0_0_0_#22d3ee]"
                : "text-ink-muted hover:bg-white/[0.04] hover:text-ink")}>
            <Icon className={cn("h-[18px] w-[18px]", active ? "text-accent" : "text-ink-faint group-hover:text-ink-muted")} />
            {label}
          </Link>
        );
      })}
      <div className="mt-auto rounded-xl border border-white/5 bg-navy-850/60 p-3 text-[11px] leading-relaxed text-ink-faint">
        Educational use only. AI-generated content can be wrong — verify against authoritative references. Not for
        diagnosis or treatment.
      </div>
    </nav>
  );
}

function AuthGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ok, setOk] = useState<boolean | null>(null);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cfg = await api.authConfig();
        if (cfg.auth_mode === "multi_user") {
          if (!getToken()) throw new Error("no token");
          await api.me();
        }
        if (!cancelled) setOk(true);
      } catch (e) {
        if ((e as Error).message === "no token" || (e as any).status === 401) {
          if (!cancelled) { setOk(false); router.replace("/login"); }
        } else if (!cancelled) setOk(true); // backend offline: shell shows the error
      }
    })();
    return () => { cancelled = true; };
  }, [router, pathname]);
  if (ok === false) return null;
  return <>{children}</>;
}

function Shell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const { backendError } = useAppStatus();
  const pathname = usePathname();
  const fullBleed = pathname.startsWith("/library/") && pathname.split("/").length > 2;
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 border-r border-white/5 bg-navy-900/60 p-4 backdrop-blur lg:block">
        <Sidebar />
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 bg-black/60 lg:hidden" onClick={() => setOpen(false)}>
          <aside className="h-full w-72 animate-fade-in border-r border-white/5 bg-navy-900 p-4" onClick={(e) => e.stopPropagation()}>
            <button aria-label="Close menu" onClick={() => setOpen(false)} className="absolute right-3 top-3 p-2 text-ink-muted"><X className="h-5 w-5" /></button>
            <Sidebar onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-white/5 bg-navy-950/80 px-4 backdrop-blur lg:px-6">
          <button aria-label="Open menu" className="rounded-lg p-1.5 text-ink-muted hover:bg-white/5 lg:hidden" onClick={() => setOpen(true)}>
            <Menu className="h-5 w-5" />
          </button>
          <div className="lg:hidden"><span className="font-bold tracking-wide text-white">MEDI-GENIUS</span></div>
          <div className="ml-auto"><AIStatusPill /></div>
        </header>
        {backendError && (
          <div className="px-4 pt-4 lg:px-6">
            <Alert tone="danger" title="Cannot reach the backend">{backendError} Start it with <code>scripts\start-backend.ps1</code>.</Alert>
          </div>
        )}
        <main className={cn("min-w-0 flex-1", fullBleed ? "" : "mx-auto w-full max-w-7xl px-4 py-6 lg:px-8 lg:py-8")}>{children}</main>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  if (pathname === "/login") return <>{children}</>;
  return (
    <AuthGate>
      <AppStatusProvider>
        <Shell>{children}</Shell>
      </AppStatusProvider>
    </AuthGate>
  );
}
