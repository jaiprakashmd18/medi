"use client";

import {
  ChevronLeft, ChevronRight, Download, Eye, FileText, Image as ImageIcon, Maximize2, ZoomIn, ZoomOut,
} from "lucide-react";
import { useEffect, useState } from "react";

import { Alert, Badge, Button, Modal, Segmented, Spinner } from "@/components/ui";
import { Markdown } from "@/features/tutor/Markdown";
import { cn } from "@/lib/utils";
import { api, assetUrl } from "@/services/api";
import type { DocImage, DocumentDetail, PageDetail } from "@/types/api";

export function Viewer({ doc, page, setPage, onExplainImage }: { doc: DocumentDetail; page: number;
  setPage: (n: number) => void; onExplainImage?: (img: DocImage) => void }) {
  const [detail, setDetail] = useState<PageDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"original" | "extracted">(doc.has_preview || doc.file_type === "image" ? "original" : "extracted");
  const [scale, setScale] = useState(1.25);
  const [imgLoading, setImgLoading] = useState(true);
  const [zoomImg, setZoomImg] = useState<DocImage | null>(null);
  const total = Math.max(1, doc.page_count);
  const unit = doc.page_kind === "slide" ? "Slide" : doc.page_kind === "section" ? "Section" : "Page";
  const canRender = doc.has_preview || doc.file_type === "image";

  useEffect(() => {
    let cancel = false;
    setLoading(true);
    setError(null);
    api.page(doc.id, page).then((d) => !cancel && setDetail(d)).catch((e) => !cancel && setError(e.message))
      .finally(() => !cancel && setLoading(false));
    setImgLoading(true);
    return () => { cancel = true; };
  }, [doc.id, page]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable) return;
      if (e.key === "ArrowRight" || e.key === "PageDown") setPage(Math.min(total, page + 1));
      if (e.key === "ArrowLeft" || e.key === "PageUp") setPage(Math.max(1, page - 1));
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [page, total, setPage]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-white/5 px-3 py-2">
        <div className="flex items-center gap-1">
          <Button size="icon" variant="ghost" aria-label={`Previous ${unit}`} disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft className="h-4 w-4" /></Button>
          <form onSubmit={(e) => { e.preventDefault(); const v = Number((e.currentTarget.elements.namedItem("pg") as HTMLInputElement).value); if (v >= 1 && v <= total) setPage(v); }}
            className="flex items-center gap-1 text-xs text-ink-muted">
            {unit} <input name="pg" key={page} defaultValue={page} aria-label={`${unit} number`} className="input h-7 w-12 px-1 py-0 text-center text-xs" /> of {total}
          </form>
          <Button size="icon" variant="ghost" aria-label={`Next ${unit}`} disabled={page >= total} onClick={() => setPage(page + 1)}><ChevronRight className="h-4 w-4" /></Button>
        </div>
        <Segmented size="sm" value={mode} onChange={setMode} options={[
          { value: "original", label: "Original" }, { value: "extracted", label: "Extracted" }]} />
        {mode === "original" && canRender && doc.file_type !== "image" && (
          <div className="flex items-center gap-0.5">
            <Button size="icon" variant="ghost" aria-label="Zoom out" disabled={scale <= 0.5} onClick={() => setScale(Math.max(0.5, scale - 0.25))}><ZoomOut className="h-4 w-4" /></Button>
            <span className="w-10 text-center text-xs text-ink-muted">{Math.round(scale * 80)}%</span>
            <Button size="icon" variant="ghost" aria-label="Zoom in" disabled={scale >= 3} onClick={() => setScale(Math.min(3, scale + 0.25))}><ZoomIn className="h-4 w-4" /></Button>
          </div>
        )}
        <a href={api.fileUrl(doc.id)} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-xs text-ink-muted hover:text-accent">
          <Download className="h-3.5 w-3.5" /> Original file
        </a>
      </div>

      <div className="min-h-0 flex-1 overflow-auto bg-navy-950/60 p-3 lg:p-5">
        {detail && detail.warnings.length > 0 && (
          <Alert tone="warn" className="mx-auto mb-3 max-w-3xl">{detail.warnings.join(" · ")}</Alert>
        )}
        {detail?.status === "failed" && <Alert tone="danger" className="mx-auto mb-3 max-w-3xl">{detail.error}</Alert>}
        {mode === "original" ? (
          canRender ? (
            <div className="relative flex justify-center">
              {imgLoading && <div className="absolute inset-0 grid place-items-center"><Spinner /></div>}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img key={`${page}-${scale}`} src={api.pageImageUrl(doc.id, page, doc.file_type === "image" ? 1 : scale * 1.6)}
                alt={`${unit} ${page} of ${doc.title}`} onLoad={() => setImgLoading(false)} onError={() => setImgLoading(false)}
                style={{ width: doc.file_type === "image" ? undefined : `${scale * 80}%` }}
                className="h-auto max-w-none rounded-lg bg-white shadow-2xl shadow-black/50 sm:max-w-none" />
            </div>
          ) : (
            <Alert tone="info" className="mx-auto max-w-3xl">
              A rendered preview is not available because LibreOffice is not installed on this computer. Showing the extracted
              content instead — install LibreOffice and reprocess the document to see slides exactly as designed.
            </Alert>
          )
        ) : null}
        {(mode === "extracted" || !canRender) && (
          loading ? <div className="flex justify-center py-10"><Spinner /></div>
            : error ? <Alert tone="danger">{error}</Alert>
              : detail && <ExtractedView d={detail} unit={unit} onZoom={setZoomImg} />
        )}
        {mode === "original" && detail && detail.images.length > 0 && (
          <div className="mx-auto mt-4 max-w-3xl">
            <div className="mb-2 flex items-center gap-2 text-xs text-ink-muted"><ImageIcon className="h-3.5 w-3.5" /> Diagrams extracted from this {unit.toLowerCase()}</div>
            <div className="flex flex-wrap gap-2">
              {detail.images.map((img) => (
                <button key={img.id} onClick={() => setZoomImg(img)} className="group relative overflow-hidden rounded-lg border border-white/10 bg-white">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={assetUrl(img.url)} alt={`Diagram ${img.index_on_page + 1}`} className="h-20 w-auto object-contain" />
                  <span className="absolute inset-0 grid place-items-center bg-black/50 opacity-0 transition group-hover:opacity-100"><Maximize2 className="h-4 w-4 text-white" /></span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <Modal open={!!zoomImg} onClose={() => setZoomImg(null)} title={`Original diagram · ${unit} ${zoomImg?.page_number}`} wide>
        {zoomImg && (
          <div className="space-y-3">
            <Badge tone="ok">Authentic source image from your document</Badge>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={assetUrl(zoomImg.url)} alt="Enlarged diagram" className="mx-auto max-h-[65vh] rounded-lg bg-white" />
            {zoomImg.ocr_text && <p className="text-xs text-ink-muted"><span className="font-semibold">Text detected (OCR):</span> {zoomImg.ocr_text}</p>}
            {onExplainImage && <Button variant="primary" onClick={() => { onExplainImage(zoomImg); setZoomImg(null); }}><Eye className="h-4 w-4" /> Explain this diagram</Button>}
          </div>
        )}
      </Modal>
    </div>
  );
}

function ExtractedView({ d, unit, onZoom }: { d: PageDetail; unit: string; onZoom: (img: DocImage) => void }) {
  const empty = !d.text && !d.tables.length && !d.images.length && !d.notes;
  return (
    <article className="mx-auto max-w-3xl space-y-4 rounded-2xl border border-white/5 bg-navy-900/80 p-5 lg:p-7">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold text-white">{d.title || `${unit} ${d.page_number}`}</h2>
        {d.ocr_used && <Badge tone="info" title="Text recognised from an image">OCR{d.ocr_confidence ? ` · ${Math.round(d.ocr_confidence)}% confidence` : ""}</Badge>}
        {d.is_scanned && <Badge>Scanned</Badge>}
      </div>
      {empty && <p className="text-sm text-ink-muted">No text was found on this {unit.toLowerCase()}.</p>}
      {d.text && <div className={cn("whitespace-pre-wrap text-[0.93rem] leading-relaxed text-ink")}>{d.text}</div>}
      {d.tables.map((t) => (
        <div key={t.index}>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink-faint">Table {t.index + 1}</div>
          <Markdown content={t.markdown} />
        </div>
      ))}
      {d.images.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {d.images.map((img) => (
            <button key={img.id} onClick={() => onZoom(img)} className="overflow-hidden rounded-lg border border-white/10 bg-white p-1">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={assetUrl(img.url)} alt={`Image ${img.index_on_page + 1}`} className="mx-auto max-h-40 object-contain" />
            </button>
          ))}
        </div>
      )}
      {d.notes && (
        <div className="rounded-xl border border-amber-400/15 bg-amber-400/[0.04] p-3">
          <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-amber-200/80"><FileText className="h-3.5 w-3.5" /> Speaker notes</div>
          <p className="whitespace-pre-wrap text-sm text-ink">{d.notes}</p>
        </div>
      )}
    </article>
  );
}
