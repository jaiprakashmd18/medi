"use client";

import { Cloud, Cpu, Eye, EyeOff, RotateCcw, Sparkles, Tag } from "lucide-react";
import { useEffect, useState } from "react";

import { Alert, Badge, Button, Segmented, Spinner } from "@/components/ui";
import { useAppStatus } from "@/hooks/useAppStatus";
import { Markdown } from "@/features/tutor/Markdown";
import { LEVELS } from "@/lib/utils";
import { api, assetUrl } from "@/services/api";
import type { DocImage, LabelBox, Source } from "@/types/api";

type Result = Awaited<ReturnType<typeof api.explainDiagram>>;

export function DiagramExplainer({ image, documentTitle, pageKind, onCite, compact }: { image: DocImage;
  documentTitle?: string; pageKind?: string; onCite?: (s: Source) => void; compact?: boolean }) {
  const { settings } = useAppStatus();
  const [level, setLevel] = useState(settings?.default_teaching_level ?? 2);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"explain" | "labels">("explain");

  useEffect(() => { setResult(null); setError(null); }, [image.id]);

  async function run() {
    setBusy(true);
    setError(null);
    try { setResult(await api.explainDiagram(image.id, level, question || undefined)); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  const sources = result ? result.sources.map((s) => ({ ...s, used_in_answer: result.used_citations.includes(s.label) })) : [];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="ok">Original source diagram</Badge>
        {documentTitle && <span className="text-xs text-ink-muted">{documentTitle} · {pageKind ?? image.page_kind ?? "page"} {image.page_number}</span>}
      </div>
      <Segmented size="sm" value={tab} onChange={setTab} options={[{ value: "explain", label: "AI explanation" }, { value: "labels", label: "Label quiz" }]} />
      {tab === "labels" ? <LabelQuiz image={image} /> : (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={assetUrl(image.url)} alt="Diagram" className={`mx-auto rounded-lg bg-white ${compact ? "max-h-56" : "max-h-[50vh]"}`} />
          {image.ocr_text && <p className="text-xs text-ink-muted"><span className="font-semibold">Labels detected (OCR):</span> {image.ocr_text}</p>}
          <div className="flex flex-wrap items-center gap-2">
            <Segmented size="sm" value={level} onChange={setLevel} options={LEVELS.map((l) => ({ value: l.level, label: `${l.level}`, title: l.long }))} />
            <span className="text-xs text-ink-faint">{LEVELS[level - 1].long}</span>
          </div>
          <div className="flex gap-2">
            <input className="input" placeholder="Optional: what do you want to know about this diagram?" value={question} onChange={(e) => setQuestion(e.target.value)} />
            <Button variant="primary" onClick={run} loading={busy}><Sparkles className="h-4 w-4" />Explain</Button>
          </div>
          {error && <Alert tone="danger">{error}</Alert>}
          {busy && <div className="flex items-center gap-2 text-sm text-ink-muted"><Spinner className="h-4 w-4" /> Analysing the diagram…</div>}
          {result && (
            <div className="rounded-2xl border border-violet-400/15 bg-violet-400/[0.03] p-4">
              <div className="mb-2 flex flex-wrap gap-1.5">
                <Badge tone="violet">AI-generated explanation</Badge>
                <Badge tone={result.provider === "anthropic" ? "accent" : "info"} title={result.routing}>
                  {result.provider === "anthropic" ? <Cloud className="h-3 w-3" /> : <Cpu className="h-3 w-3" />}{result.model}
                </Badge>
                <Badge tone={result.vision_used ? "ok" : "warn"}>{result.vision_used ? "Image analysed visually" : "Text-only (no vision model)"}</Badge>
              </div>
              {result.notice && <Alert tone="warn" className="mb-2">{result.notice}</Alert>}
              <Markdown content={result.explanation} sources={sources} onCite={onCite} />
              <p className="mt-3 text-[11px] text-ink-faint">Visual identification by AI can be wrong. Check labels against your textbook or atlas.</p>
            </div>
          )}
          {!result && image.ai_description && !busy && (
            <details className="text-sm"><summary className="cursor-pointer text-xs text-ink-muted">Previous AI explanation ({image.ai_provider} · {image.ai_model})</summary>
              <div className="mt-2"><Markdown content={image.ai_description} /></div></details>
          )}
        </>
      )}
    </div>
  );
}

/** Masks OCR-located labels on the ORIGINAL diagram for self-testing. Nothing is invented: only detected labels are used. */
export function LabelQuiz({ image }: { image: DocImage }) {
  const [data, setData] = useState<{ width: number; height: number; labels: LabelBox[]; ocr_available: boolean; note: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revealed, setRevealed] = useState<Set<number>>(new Set());
  const [guesses, setGuesses] = useState<Record<number, string>>({});
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    setData(null); setRevealed(new Set()); setGuesses({}); setChecked(false);
    api.imageLabels(image.id).then(setData).catch((e) => setError(e.message));
  }, [image.id]);

  if (error) return <Alert tone="danger">{error}</Alert>;
  if (!data) return <div className="flex justify-center py-6"><Spinner /></div>;
  if (!data.ocr_available || data.labels.length === 0)
    return <Alert tone="info">{data.ocr_available ? "No text labels were detected on this diagram, so a label quiz is not possible." : data.note}</Alert>;

  const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
  const score = data.labels.filter((l, i) => norm(guesses[i] ?? "") === norm(l.text)).length;

  return (
    <div className="space-y-3">
      <p className="text-xs text-ink-muted">Labels detected on the original image are hidden. Name each numbered label, then check your answers.</p>
      <div className="relative mx-auto w-full max-w-2xl overflow-hidden rounded-lg bg-white">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={assetUrl(image.url)} alt="Diagram with hidden labels" className="block w-full" />
        {data.labels.map((l, i) => !revealed.has(i) && (
          <button key={i} onClick={() => setRevealed(new Set(revealed).add(i))} title="Click to reveal"
            className="absolute grid place-items-center rounded bg-navy-800 text-[11px] font-bold text-accent ring-1 ring-accent/60"
            style={{ left: `${(100 * l.left) / data.width}%`, top: `${(100 * l.top) / data.height}%`,
              width: `${(100 * l.width) / data.width}%`, height: `${Math.max((100 * l.height) / data.height, 3)}%` }}>{i + 1}</button>
        ))}
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {data.labels.map((l, i) => {
          const ok = norm(guesses[i] ?? "") === norm(l.text);
          return (
            <label key={i} className="flex items-center gap-2 text-sm">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded bg-navy-700 text-[11px] font-bold text-accent">{i + 1}</span>
              <input className="input h-8 py-1" value={guesses[i] ?? ""} onChange={(e) => setGuesses({ ...guesses, [i]: e.target.value })} aria-label={`Label ${i + 1}`} />
              {checked && (ok ? <Badge tone="ok">✓</Badge> : <Badge tone="danger" title={l.text}>{l.text}</Badge>)}
            </label>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" size="sm" onClick={() => setChecked(true)}><Tag className="h-3.5 w-3.5" />Check answers</Button>
        <Button size="sm" onClick={() => setRevealed(new Set(data.labels.map((_, i) => i)))}><Eye className="h-3.5 w-3.5" />Reveal all</Button>
        <Button size="sm" variant="ghost" onClick={() => { setRevealed(new Set()); setGuesses({}); setChecked(false); }}><RotateCcw className="h-3.5 w-3.5" />Reset</Button>
        {checked && <span className="self-center text-sm text-ink">{score} / {data.labels.length} correct</span>}
      </div>
      <p className="flex items-center gap-1 text-[11px] text-ink-faint"><EyeOff className="h-3 w-3" />{data.note}</p>
    </div>
  );
}
