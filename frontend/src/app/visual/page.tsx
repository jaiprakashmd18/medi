"use client";

import { Image as ImageIcon, Shapes } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Alert, Badge, Card, EmptyState, Modal, PageHeader, Spinner } from "@/components/ui";
import { DiagramExplainer } from "@/features/visual/DiagramExplainer";
import { useAppStatus } from "@/hooks/useAppStatus";
import { useAsync } from "@/hooks/useAsync";
import { api, assetUrl } from "@/services/api";
import type { DocImage } from "@/types/api";

export default function VisualPage() {
  const { subjects } = useAppStatus();
  const [subjectId, setSubjectId] = useState<number | null>(null);
  const [labelledOnly, setLabelledOnly] = useState(false);
  const imgs = useAsync(() => api.allImages({ subject_id: subjectId }), [subjectId]);
  const [open, setOpen] = useState<DocImage | null>(null);
  const list = useMemo(() => (imgs.data ?? []).filter((i) => !labelledOnly || i.ocr_text.trim()), [imgs.data, labelledOnly]);

  return (
    <div>
      <PageHeader title="Visual Learning" icon={<ImageIcon />}
        subtitle="Diagrams and images extracted from your documents. Enlarge, get AI explanations, and test yourself on labels." />
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <select className="input w-52" value={subjectId ?? ""} onChange={(e) => setSubjectId(e.target.value ? Number(e.target.value) : null)} aria-label="Subject">
          <option value="">All subjects</option>
          {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <label className="flex items-center gap-2 text-sm text-ink-muted">
          <input type="checkbox" checked={labelledOnly} onChange={(e) => setLabelledOnly(e.target.checked)} className="accent-cyan-400" />
          Only diagrams with detected labels
        </label>
        <span className="text-xs text-ink-faint sm:ml-auto">All images shown are authentic content from your uploads.</span>
      </div>
      {imgs.error && <Alert tone="danger">{imgs.error.message}</Alert>}
      {imgs.loading ? <div className="flex justify-center py-12"><Spinner /></div> : list.length === 0 ? (
        <EmptyState icon={<Shapes />} title="No diagrams yet" action={<Link href="/library" className="text-sm text-accent hover:underline">Upload documents →</Link>}>
          Upload PDFs or slides containing diagrams; extracted images appear here automatically.
        </EmptyState>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {list.map((img) => (
            <Card key={img.id} className="card-hover cursor-pointer overflow-hidden" onClick={() => setOpen(img)}>
              <div className="grid h-40 place-items-center bg-white p-2">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={assetUrl(img.url)} alt={`Diagram from ${img.document_title}`} loading="lazy" className="max-h-full max-w-full object-contain" />
              </div>
              <div className="p-3">
                <div className="truncate text-sm font-medium text-white">{img.document_title}</div>
                <div className="mt-1 flex flex-wrap gap-1">
                  <Badge>{img.page_kind} {img.page_number}</Badge>
                  {img.ocr_text.trim() && <Badge tone="info">Labelled</Badge>}
                  {img.ai_description && <Badge tone="violet">Explained</Badge>}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
      <Card className="mt-8 p-5">
        <h2 className="section-title mb-2">Coming later</h2>
        <p className="text-sm text-ink-muted">
          AI-generated study illustrations and interactive 3D anatomy (Three.js with licensed anatomy assets) are planned.
          They will always be clearly labelled as AI-generated and kept separate from your authentic source diagrams.
        </p>
      </Card>
      <Modal open={!!open} onClose={() => setOpen(null)} title="Diagram study" wide>
        {open && <DiagramExplainer image={open} documentTitle={open.document_title} pageKind={open.page_kind}
          onCite={(s) => s.document_id && window.location.assign(`/library/${s.document_id}?page=${s.page_number}`)} />}
      </Modal>
    </div>
  );
}
