"use client";

import { ArrowRight, Bot, ChevronLeft, PanelLeft, PanelRight, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";

import { Alert, Badge, Button, ProgressBar, Segmented, Spinner } from "@/components/ui";
import { DiagramExplainer } from "@/features/visual/DiagramExplainer";
import { ChatView } from "@/features/tutor/ChatView";
import { Viewer } from "@/features/workspace/Viewer";
import { useAsync, usePolling } from "@/hooks/useAsync";
import { cn, isProcessing, PROCESSING_LABELS } from "@/lib/utils";
import { api } from "@/services/api";
import type { DocImage, DocumentDetail, PageSummary, Source } from "@/types/api";

function useResizable(initial: number, min: number, max: number, side: "left" | "right") {
  const [w, setW] = useState(initial);
  const drag = useRef<{ x: number; w: number } | null>(null);
  const onDown = (e: React.PointerEvent) => {
    drag.current = { x: e.clientX, w };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onMove = (e: React.PointerEvent) => {
    if (!drag.current) return;
    const dx = e.clientX - drag.current.x;
    setW(Math.max(min, Math.min(max, drag.current.w + (side === "left" ? dx : -dx))));
  };
  const onUp = () => { drag.current = null; };
  return { w, handle: { onPointerDown: onDown, onPointerMove: onMove, onPointerUp: onUp } };
}

function Outline({ doc, pages, page, setPage }: { doc: DocumentDetail; pages: PageSummary[]; page: number; setPage: (n: number) => void }) {
  const unit = doc.page_kind === "slide" ? "Slide" : doc.page_kind === "section" ? "Section" : "Page";
  return (
    <div className="h-full overflow-y-auto p-3">
      {doc.outline.length > 0 && (
        <section className="mb-4">
          <h3 className="mb-1.5 px-2 text-[11px] font-semibold uppercase tracking-wider text-ink-faint">Contents</h3>
          <ul>
            {doc.outline.map((o, i) => (
              <li key={i}>
                <button onClick={() => setPage(o.page)} style={{ paddingLeft: `${(o.level - 1) * 12 + 8}px` }}
                  className={cn("w-full truncate rounded-lg py-1.5 pr-2 text-left text-[13px] transition hover:bg-white/5",
                    o.page === page ? "text-accent-soft" : "text-ink-muted")}>{o.title}</button>
              </li>
            ))}
          </ul>
        </section>
      )}
      <h3 className="mb-1.5 px-2 text-[11px] font-semibold uppercase tracking-wider text-ink-faint">{unit}s</h3>
      <ul className="space-y-0.5">
        {pages.map((p) => (
          <li key={p.page_number}>
            <button onClick={() => setPage(p.page_number)} aria-current={p.page_number === page ? "page" : undefined}
              className={cn("flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[13px] transition",
                p.page_number === page ? "bg-accent/10 text-white shadow-[inset_2px_0_0_0_#22d3ee]" : "text-ink-muted hover:bg-white/5")}>
              <span className="w-6 shrink-0 text-right text-[11px] text-ink-faint">{p.page_number}</span>
              <span className="min-w-0 flex-1 truncate">{p.title || <span className="italic text-ink-faint">{p.char_count ? `${unit} ${p.page_number}` : "No text"}</span>}</span>
              {p.status !== "ok" && <span className={cn("h-1.5 w-1.5 rounded-full", p.status === "failed" ? "bg-rose-400" : "bg-amber-400")} title={p.status} />}
              {p.ocr_used && <span className="text-[9px] font-semibold text-sky-300">OCR</span>}
              {p.image_count > 0 && <span className="text-[9px] text-ink-faint">{p.image_count}img</span>}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Workspace() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const router = useRouter();
  const doc = useAsync(() => api.document(id), [id]);
  const pages = useAsync(() => api.pages(id), [id]);
  const [page, setPageState] = useState<number>(Number(params.get("page")) || 0);
  const [conversationId, setConversationId] = useState<string | null>(params.get("conversation"));
  const [chatKey, setChatKey] = useState(0);
  const [showLeft, setShowLeft] = useState(true);
  const [showRight, setShowRight] = useState(true);
  const [mobileTab, setMobileTab] = useState<"outline" | "document" | "tutor">("document");
  const [diagram, setDiagram] = useState<DocImage | null>(null);
  const left = useResizable(260, 180, 420, "left");
  const right = useResizable(440, 320, 760, "right");
  const processing = doc.data ? isProcessing(doc.data.status) : false;
  usePolling(() => { doc.reload(true); pages.reload(true); }, 1500, processing);

  useEffect(() => {
    if (doc.data && !page) setPageState(Math.min(doc.data.last_page_viewed || 1, Math.max(1, doc.data.page_count)));
  }, [doc.data, page]);

  // remember reading position (debounced)
  useEffect(() => {
    if (!page || !doc.data || processing) return;
    const t = setTimeout(() => api.markViewed(id, page).catch(() => {}), 800);
    return () => clearTimeout(t);
  }, [id, page, doc.data, processing]);

  const setPage = useCallback((n: number) => { setPageState(n); setMobileTab((t) => (t === "outline" ? "document" : t)); }, []);

  const onCite = useCallback((s: Source) => {
    if (s.document_id === id) { setPageState(s.page_number); setMobileTab("document"); }
    else if (s.document_id) router.push(`/library/${s.document_id}?page=${s.page_number}`);
  }, [id, router]);

  if (doc.error) return <div className="p-6"><Alert tone="danger">{doc.error.message}</Alert></div>;
  if (!doc.data) return <div className="flex justify-center p-12"><Spinner /></div>;
  const d = doc.data;
  const unit = d.page_kind === "slide" ? "slide" : d.page_kind === "section" ? "section" : "page";

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-white/5 bg-navy-900/40 px-3 py-2 lg:px-4">
        <Link href="/library" className="rounded-lg p-1 text-ink-muted hover:bg-white/5 hover:text-ink" aria-label="Back to library"><ChevronLeft className="h-5 w-5" /></Link>
        <h1 className="min-w-0 flex-1 truncate text-sm font-semibold text-white lg:text-base">{d.title}</h1>
        {d.status === "partial" && <Badge tone="warn" title={d.warnings.join("\n")}>Partially processed</Badge>}
        <div className="hidden items-center gap-1 lg:flex">
          <Button size="icon" variant={showLeft ? "outline" : "ghost"} aria-label="Toggle outline panel" onClick={() => setShowLeft(!showLeft)}><PanelLeft className="h-4 w-4" /></Button>
          <Button size="icon" variant={showRight ? "outline" : "ghost"} aria-label="Toggle tutor panel" onClick={() => setShowRight(!showRight)}><PanelRight className="h-4 w-4" /></Button>
        </div>
      </div>

      {processing || d.status === "failed" ? (
        <div className="mx-auto mt-10 w-full max-w-lg px-4">
          {d.status === "failed" ? (
            <Alert tone="danger" title="Processing failed">
              {d.error_message}
              <div className="mt-3"><Button size="sm" onClick={async () => { await api.reprocess(d.id); doc.reload(); }}><RefreshCw className="h-3.5 w-3.5" /> Retry processing</Button></div>
            </Alert>
          ) : (
            <div className="card p-6 text-center">
              <Spinner className="mx-auto mb-3 h-7 w-7" />
              <div className="font-medium text-white">{PROCESSING_LABELS[d.status]}…</div>
              <div className="mt-1 text-sm text-ink-muted">{d.stage_message}</div>
              <ProgressBar value={d.progress} className="mt-4" />
            </div>
          )}
        </div>
      ) : (
        <>
          <div className="flex border-b border-white/5 px-3 py-1.5 lg:hidden">
            <Segmented value={mobileTab} onChange={setMobileTab} className="w-full justify-between" options={[
              { value: "outline", label: "Outline" }, { value: "document", label: "Document" }, { value: "tutor", label: "AI Tutor" }]} />
          </div>
          <div className="flex min-h-0 flex-1">
            {showLeft && (
              <aside className={cn("min-h-0 shrink-0 border-r border-white/5 bg-navy-900/40", mobileTab === "outline" ? "block w-full" : "hidden", "lg:block lg:w-[var(--pw)]")}
                style={{ "--pw": `${left.w}px` } as React.CSSProperties}>
                <Outline doc={d} pages={pages.data ?? []} page={page || 1} setPage={setPage} />
              </aside>
            )}
            {showLeft && <div className="hidden w-1 cursor-col-resize bg-transparent transition hover:bg-accent/30 lg:block" {...left.handle} aria-hidden />}
            <section className={cn("min-h-0 min-w-0 flex-1", mobileTab === "document" ? "block" : "hidden", "lg:block")}>
              {page > 0 && <Viewer doc={d} page={page} setPage={setPage} onExplainImage={(img) => { setDiagram(img); setMobileTab("tutor"); }} />}
            </section>
            {showRight && <div className="hidden w-1 cursor-col-resize bg-transparent transition hover:bg-accent/30 lg:block" {...right.handle} aria-hidden />}
            {showRight && (
              <aside className={cn("min-h-0 shrink-0 border-l border-white/5 bg-navy-900/50", mobileTab === "tutor" ? "flex w-full" : "hidden", "flex-col lg:flex lg:w-[var(--pw)]")}
                style={{ "--pw": `${right.w}px` } as React.CSSProperties}>
                <div className="flex items-center gap-2 border-b border-white/5 px-3 py-2">
                  <Bot className="h-4 w-4 text-accent" />
                  <span className="text-sm font-semibold text-white">AI Medical Tutor</span>
                  <span className="truncate text-xs text-ink-faint">· {unit} {page}</span>
                  {conversationId && <button className="ml-auto text-[11px] text-ink-faint hover:text-accent" onClick={() => { setConversationId(null); setChatKey((k) => k + 1); }}>New chat</button>}
                </div>
                {diagram ? (
                  <div className="min-h-0 flex-1 overflow-y-auto p-3">
                    <button className="mb-2 inline-flex items-center gap-1 text-xs text-ink-muted hover:text-accent" onClick={() => setDiagram(null)}>
                      <ArrowRight className="h-3 w-3 rotate-180" /> Back to chat</button>
                    <DiagramExplainer image={diagram} documentTitle={d.title} pageKind={unit} onCite={onCite} compact />
                  </div>
                ) : (
                  <div className="min-h-0 flex-1">
                    <ChatView key={chatKey} compact documentIds={[d.id]} pageNumber={page || null}
                      pageLabel={`${unit} ${page}`} conversationId={conversationId}
                      onConversation={setConversationId} onCite={onCite} />
                  </div>
                )}
              </aside>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function WorkspacePage() {
  return <Suspense fallback={<div className="flex justify-center p-12"><Spinner /></div>}><Workspace /></Suspense>;
}
