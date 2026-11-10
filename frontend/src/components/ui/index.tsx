"use client";

import { CircleAlert, Info, LoaderCircle, X } from "lucide-react";
import { type ButtonHTMLAttributes, type ReactNode, useEffect } from "react";

import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "outline";
const variants: Record<Variant, string> = {
  primary: "bg-gradient-to-r from-cyan-400 to-teal-400 text-navy-950 font-semibold hover:brightness-110 shadow-glow",
  secondary: "bg-navy-700 text-ink hover:bg-navy-600 border border-white/5",
  outline: "border border-accent/40 text-accent hover:bg-accent/10",
  ghost: "text-ink-muted hover:text-ink hover:bg-white/5",
  danger: "bg-rose-500/15 text-rose-300 border border-rose-400/30 hover:bg-rose-500/25",
};

export function Button({ variant = "secondary", size = "md", loading, className, children, disabled, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" | "lg" | "icon"; loading?: boolean }) {
  const sizes = { sm: "h-8 px-3 text-xs gap-1.5", md: "h-10 px-4 text-sm gap-2", lg: "h-12 px-6 text-base gap-2",
    icon: "h-9 w-9 justify-center" };
  return (
    <button
      className={cn("focus-ring inline-flex shrink-0 items-center rounded-xl transition disabled:cursor-not-allowed disabled:opacity-50",
        variants[variant], sizes[size], className)}
      disabled={disabled || loading} {...rest}>
      {loading && <LoaderCircle className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
}

export function Card({ className, children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("card", className)} {...rest}>{children}</div>;
}

export function Badge({ children, tone = "default", className, title }: { children: ReactNode; tone?:
  "default" | "accent" | "warn" | "danger" | "ok" | "info" | "violet"; className?: string; title?: string }) {
  const tones = {
    default: "border-white/10 bg-white/5 text-ink-muted",
    accent: "border-accent/30 bg-accent/10 text-accent-soft",
    warn: "border-amber-400/30 bg-amber-400/10 text-amber-300",
    danger: "border-rose-400/30 bg-rose-400/10 text-rose-300",
    ok: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
    info: "border-sky-400/30 bg-sky-400/10 text-sky-300",
    violet: "border-violet-400/30 bg-violet-400/10 text-violet-300",
  };
  return <span title={title} className={cn("chip", tones[tone], className)}>{children}</span>;
}

export function Spinner({ className }: { className?: string }) {
  return <LoaderCircle className={cn("h-5 w-5 animate-spin text-accent", className)} />;
}

export function ProgressBar({ value, className, tone = "accent" }: { value: number; className?: string; tone?: "accent" | "warn" | "danger" }) {
  const c = { accent: "from-cyan-400 to-teal-400", warn: "from-amber-400 to-amber-300", danger: "from-rose-500 to-rose-400" }[tone];
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-white/5", className)} role="progressbar"
      aria-valuenow={Math.round(value)} aria-valuemin={0} aria-valuemax={100}>
      <div className={cn("h-full rounded-full bg-gradient-to-r transition-all duration-500", c)}
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

export function EmptyState({ icon, title, children, action }: { icon: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      <div className="mb-4 grid h-14 w-14 place-items-center rounded-2xl border border-accent/20 bg-accent/5 text-accent">{icon}</div>
      <h3 className="text-base font-semibold text-white">{title}</h3>
      {children && <div className="mt-1.5 max-w-md text-sm text-ink-muted">{children}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Alert({ tone = "info", title, children, onClose, className }: { tone?: "info" | "warn" | "danger";
  title?: string; children?: ReactNode; onClose?: () => void; className?: string }) {
  const styles = { info: "border-sky-400/25 bg-sky-400/[0.06] text-sky-200", warn: "border-amber-400/25 bg-amber-400/[0.06] text-amber-200",
    danger: "border-rose-400/25 bg-rose-400/[0.07] text-rose-200" };
  const Icon = tone === "info" ? Info : CircleAlert;
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cn("flex gap-3 rounded-xl border px-3.5 py-3 text-sm", styles[tone], className)}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 flex-1">
        {title && <div className="font-semibold">{title}</div>}
        {children && <div className="mt-0.5 break-words opacity-90">{children}</div>}
      </div>
      {onClose && <button aria-label="Dismiss" onClick={onClose} className="opacity-70 hover:opacity-100"><X className="h-4 w-4" /></button>}
    </div>
  );
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: string;
  children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 backdrop-blur-sm sm:items-center sm:p-6"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-label={title}
        className={cn("card max-h-[92vh] w-full animate-fade-in overflow-hidden rounded-b-none sm:rounded-2xl",
          wide ? "sm:max-w-5xl" : "sm:max-w-lg")}>
        <div className="flex items-center justify-between border-b border-white/5 px-5 py-3.5">
          <h2 className="font-semibold text-white">{title}</h2>
          <button aria-label="Close" onClick={onClose} className="rounded-lg p-1 text-ink-muted hover:bg-white/5 hover:text-ink"><X className="h-5 w-5" /></button>
        </div>
        <div className="max-h-[calc(92vh-56px)] overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions, icon }: { title: string; subtitle?: string; actions?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="flex items-center gap-3">
        {icon && <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-accent/20 bg-accent/10 text-accent">{icon}</div>}
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-white">{title}</h1>
          {subtitle && <p className="mt-0.5 text-sm text-ink-muted">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Segmented<T extends string | number>({ value, onChange, options, className, size = "md" }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: string; title?: string }[]; className?: string; size?: "sm" | "md" }) {
  return (
    <div role="radiogroup" className={cn("inline-flex flex-wrap gap-1 rounded-xl border border-white/5 bg-navy-850 p-1", className)}>
      {options.map((o) => (
        <button key={String(o.value)} role="radio" aria-checked={o.value === value} title={o.title}
          onClick={() => onChange(o.value)}
          className={cn("focus-ring rounded-lg font-medium transition", size === "sm" ? "px-2 py-1 text-[11px]" : "px-3 py-1.5 text-xs",
            o.value === value ? "bg-accent/15 text-accent-soft shadow-[inset_0_0_0_1px_rgba(34,211,238,0.35)]" : "text-ink-muted hover:text-ink")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Toggle({ checked, onChange, label, id }: { checked: boolean; onChange: (v: boolean) => void; label: string; id?: string }) {
  return (
    <button id={id} role="switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)}
      className={cn("focus-ring relative h-6 w-11 shrink-0 rounded-full transition", checked ? "bg-accent" : "bg-navy-600")}>
      <span className={cn("absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition", checked ? "left-[22px]" : "left-0.5")} />
    </button>
  );
}

export function Stat({ label, value, hint, icon }: { label: string; value: ReactNode; hint?: string; icon?: ReactNode }) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between text-ink-muted">
        <span className="text-xs font-medium uppercase tracking-wider">{label}</span>
        {icon}
      </div>
      <div className="mt-2 text-2xl font-semibold text-white">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-ink-faint">{hint}</div>}
    </Card>
  );
}
