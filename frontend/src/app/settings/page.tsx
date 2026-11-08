"use client";

import { Cloud, Cpu, Download, RefreshCw, Settings, ShieldCheck, Trash2, Volume2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Alert, Badge, Button, Card, PageHeader, Segmented, Spinner, Toggle } from "@/components/ui";
import { useAppStatus } from "@/hooks/useAppStatus";
import { useAsync } from "@/hooks/useAsync";
import { useSpeechSynthesis } from "@/hooks/useSpeech";
import { LEVELS } from "@/lib/utils";
import { api, getToken, setToken } from "@/services/api";
import type { AIMode, UserSettings } from "@/types/api";

export default function SettingsPage() {
  const { settings, setSettings, providers, refresh } = useAppStatus();
  const health = useAsync(() => api.health(), []);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [name, setName] = useState(settings?.display_name ?? "");
  const [confirmText, setConfirmText] = useState("");
  const tts = useSpeechSynthesis(settings?.voice_rate ?? 1, settings?.voice_name);
  useEffect(() => { if (settings?.display_name) setName(settings.display_name); }, [settings?.display_name]);

  async function update(patch: Partial<UserSettings>) {
    setSaving(true);
    try { const s = await api.updateSettings(patch); setSettings(s); await refresh(); setMsg("Saved"); setTimeout(() => setMsg(null), 1500); }
    catch (e) { setMsg((e as Error).message); } finally { setSaving(false); }
  }

  if (!settings) return <div className="flex justify-center py-12"><Spinner /></div>;

  return (
    <div className="max-w-4xl">
      <PageHeader title="Settings" icon={<Settings />} subtitle="AI providers, privacy, teaching defaults, voice and your data."
        actions={msg ? <Badge tone={msg === "Saved" ? "ok" : "danger"}>{msg}</Badge> : saving ? <Spinner className="h-4 w-4" /> : null} />

      <Card className="mb-5 p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold text-white">AI & Privacy</h2>
          <Button size="sm" variant="ghost" loading={refreshing} onClick={async () => { setRefreshing(true); await refresh(true); setRefreshing(false); }}>
            <RefreshCw className="h-3.5 w-3.5" />Check providers</Button>
        </div>
        <label className="label">AI mode</label>
        <Segmented value={settings.ai_mode} onChange={(v: AIMode) => update({ ai_mode: v })} options={[
          { value: "auto", label: "Automatic", title: "Advanced explanations on Claude (with consent), simple tasks local" },
          { value: "local_only", label: "Local only", title: "Everything stays on this computer (Ollama)" },
          { value: "cloud_only", label: "Cloud only", title: "Always use Claude" }]} />
        <p className="mt-2 text-xs text-ink-muted">
          {settings.ai_mode === "auto" && "Document extraction, OCR, embeddings and search always run locally. Advanced teaching uses Claude when configured and permitted; otherwise the local model."}
          {settings.ai_mode === "local_only" && "Nothing is sent to the cloud. Requires Ollama running with the configured model."}
          {settings.ai_mode === "cloud_only" && "All AI teaching uses the Claude API. Requires an API key and your consent below."}
        </p>

        <div className="mt-5 flex items-start gap-3 rounded-xl border border-white/5 bg-navy-850/60 p-4">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-accent" />
          <div className="flex-1">
            <div className="font-medium text-white">Allow sending document excerpts to Claude (Anthropic)</div>
            <p className="mt-1 text-xs text-ink-muted">
              When enabled, the passages retrieved for each question (and diagrams you ask about) are sent to the Anthropic API to
              generate explanations. Whole documents are never uploaded. Without consent, MEDI-GENIUS uses only local models.
              {settings.cloud_consent_at && ` Consent given ${new Date(settings.cloud_consent_at).toLocaleString()}.`}
            </p>
          </div>
          <Toggle checked={settings.cloud_consent} onChange={(v) => update({ cloud_consent: v })} label="Cloud consent" />
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          {providers?.providers.map((p) => (
            <div key={p.name} className="rounded-xl border border-white/5 bg-navy-850/60 p-4">
              <div className="flex items-center gap-2">
                {p.kind === "cloud" ? <Cloud className="h-4 w-4 text-accent" /> : <Cpu className="h-4 w-4 text-sky-300" />}
                <span className="font-medium text-white">{p.label}</span>
                <Badge tone={p.available ? "ok" : p.configured ? "danger" : "default"} className="ml-auto">{p.available ? "Available" : p.configured ? "Unavailable" : "Not configured"}</Badge>
              </div>
              <p className="mt-2 text-xs text-ink-muted">{p.detail}</p>
              <div className="mt-2 flex flex-wrap gap-1">{Object.entries(p.models).map(([k, v]) => <Badge key={k}>{k}: {v}</Badge>)}</div>
            </div>
          ))}
        </div>
        {providers && (
          <div className="mt-4 space-y-1 text-xs">
            <div className="section-title mb-1">Current routing</div>
            {Object.entries(providers.routes).map(([task, r]) => (
              <div key={task} className="flex gap-2"><span className="w-20 capitalize text-ink-muted">{task}</span>
                <span className={r.ok ? "text-ink" : "text-amber-300"}>{r.ok ? `${r.provider} · ${r.model}` : r.reason}</span></div>
            ))}
          </div>
        )}
        <Alert tone="info" className="mt-4">
          {providers?.billing_note} To enable Claude, set <code>ANTHROPIC_API_KEY</code> in the backend <code>.env</code> file and restart the backend.
          API keys are never exposed to this browser.
        </Alert>
      </Card>

      <Card className="mb-5 p-5">
        <h2 className="mb-4 font-semibold text-white">Learning</h2>
        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <label className="label">Default teaching level</label>
            <select className="input" value={settings.default_teaching_level} onChange={(e) => update({ default_teaching_level: Number(e.target.value) })}>
              {LEVELS.map((l) => <option key={l.level} value={l.level}>Level {l.level} — {l.long}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Daily flashcard goal</label>
            <input type="number" min={1} max={500} className="input" defaultValue={settings.daily_review_goal}
              onBlur={(e) => update({ daily_review_goal: Number(e.target.value) })} />
          </div>
          <div>
            <label className="label">Display name</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} onBlur={() => name && name !== settings.display_name && update({ display_name: name })} />
          </div>
        </div>
      </Card>

      <Card className="mb-5 p-5">
        <h2 className="mb-1 flex items-center gap-2 font-semibold text-white"><Volume2 className="h-4 w-4 text-accent" />Voice tutor</h2>
        <p className="mb-4 text-xs text-ink-muted">Uses your browser’s built-in speech engine (Chrome or Edge recommended). Speech recognition may be processed by your browser vendor’s service.</p>
        {!tts.supported ? <Alert tone="warn">This browser does not support speech synthesis.</Alert> : (
          <div className="grid gap-5 sm:grid-cols-2">
            <div>
              <label className="label">Speech speed · {settings.voice_rate.toFixed(2)}×</label>
              <input type="range" min={0.5} max={2} step={0.05} defaultValue={settings.voice_rate} className="w-full accent-cyan-400"
                onMouseUp={(e) => update({ voice_rate: Number((e.target as HTMLInputElement).value) })}
                onTouchEnd={(e) => update({ voice_rate: Number((e.target as HTMLInputElement).value) })} />
            </div>
            <div>
              <label className="label">Voice</label>
              <select className="input" value={settings.voice_name ?? ""} onChange={(e) => update({ voice_name: e.target.value || null })}>
                <option value="">Default English voice</option>
                {tts.voices.filter((v) => v.lang.startsWith("en")).map((v) => <option key={v.name} value={v.name}>{v.name} ({v.lang})</option>)}
              </select>
            </div>
            <Button size="sm" className="w-fit" onClick={() => tts.speak("test", "The brachial plexus is formed by the ventral rami of C5 to T1.")}>Test voice</Button>
          </div>
        )}
      </Card>

      <Card className="mb-5 p-5">
        <h2 className="mb-4 font-semibold text-white">System status</h2>
        {health.loading ? <Spinner /> : health.data && (
          <div className="grid gap-2 sm:grid-cols-2">
            {Object.entries(health.data.checks).map(([k, v]) => (
              <div key={k} className="flex items-center gap-2 rounded-lg bg-navy-850/60 px-3 py-2 text-xs">
                <span className={`h-2 w-2 rounded-full ${v.ok ? "bg-emerald-400" : "bg-amber-400"}`} />
                <span className="w-28 capitalize text-ink">{k.replace("_", " ")}</span>
                <span className="truncate text-ink-muted">{String(v.detail ?? v.backend ?? "")}</span>
              </div>
            ))}
          </div>
        )}
        <p className="mt-3 text-[11px] text-ink-faint">Version {health.data?.version} · auth mode {health.data?.auth_mode}</p>
      </Card>

      <Card className="p-5">
        <h2 className="mb-4 font-semibold text-white">Your data</h2>
        <div className="flex flex-wrap gap-2">
          <a href={api.exportUrl()}><Button><Download className="h-4 w-4" />Export my learning data</Button></a>
          {getToken() && <Button variant="ghost" onClick={() => { setToken(null); window.location.assign("/login"); }}>Sign out</Button>}
        </div>
        <div className="mt-5 rounded-xl border border-rose-400/20 bg-rose-400/[0.04] p-4">
          <div className="font-medium text-rose-200">Delete all my data</div>
          <p className="mt-1 text-xs text-ink-muted">Permanently deletes every document, extracted file, search index entry, conversation, quiz, flashcard and progress record. This cannot be undone.</p>
          <div className="mt-3 flex gap-2">
            <input className="input max-w-[200px]" placeholder="Type DELETE" value={confirmText} onChange={(e) => setConfirmText(e.target.value)} aria-label="Confirm deletion" />
            <Button variant="danger" disabled={confirmText !== "DELETE"} onClick={async () => { await api.deleteAllData(); setConfirmText(""); setMsg("All data deleted"); }}>
              <Trash2 className="h-4 w-4" />Delete everything</Button>
          </div>
        </div>
        <p className="mt-5 text-xs leading-relaxed text-ink-faint">
          MEDI-GENIUS is a medical education tool. It does not provide diagnosis or treatment advice. AI-generated content may be
          incomplete or wrong; always verify against authoritative references and your teachers.
        </p>
      </Card>
    </div>
  );
}
