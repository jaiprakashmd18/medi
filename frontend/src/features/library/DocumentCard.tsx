"use client";

import { CircleAlert, FileImage, FileText, Pencil, Presentation, RefreshCw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge, Button, ProgressBar } from "@/components/ui";
import { cn, formatBytes, isProcessing, PROCESSING_LABELS, timeAgo } from "@/lib/utils";
import { api } from "@/services/api";
import type { DocumentSummary, Subject } from "@/types/api";

export const FileIcon = ({ type, className }: { type: string; className?: string }) => {
  const Icon = type === "pptx" ? Presentation : type === "image" ? FileImage : FileText;
  return <Icon className={className} />;
};

export function DocumentCard({ doc, subjects, onChanged }: { doc: DocumentSummary; subjects: Subject[]; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(doc.title);
  const [busy, setBusy] = useState(false);
  const subject = subjects.find((s) => s.id === doc.subject_id);
  const processing = isProcessing(doc.status);
  const unit = doc.file_type === "pptx" ? "slides" : doc.file_type === "docx" ? "sections" : "pages";

  async function save() {
    setBusy(true);
    try { await api.updateDocument(doc.id, { title }); setEditing(false); onChanged(); } finally { setBusy(false); }
  }
  async function remove() {
    if (!confirm(`Delete "${doc.title}"? This permanently removes the file, extracted content, search index and links.`)) return;
    setBusy(true);
    try { await api.deleteDocument(doc.id); onChanged(); } finally { setBusy(false); }
  }

  return (
    <div className={cn("card card-hover flex flex-col p-4", doc.status === "failed" && "border-rose-400/20")} data-testid="document-card">
      <div className="flex items-start gap-3">
        <div className={cn("grid h-11 w-11 shrink-0 place-items-center rounded-xl border",
          doc.file_type === "pptx" ? "border-amber-400/20 bg-amber-400/10 text-amber-300" : doc.file_type === "image"
            ? "border-violet-400/20 bg-violet-400/10 text-violet-300" : "border-accent/20 bg-accent/10 text-accent")}>
          <FileIcon type={doc.file_type} className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          {editing ? (
            <form onSubmit={(e) => { e.preventDefault(); save(); }} className="flex gap-1.5">
              <input autoFocus className="input h-8 py-1" value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Document title" />
              <Button size="sm" type="submit" loading={busy}>Save</Button>
            </form>
          ) : (
            <Link href={`/library/${doc.id}`} className="line-clamp-2 font-medium text-white hover:text-accent-soft">{doc.title}</Link>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-ink-faint">
            <span className="uppercase">{doc.file_type}</span>·<span>{formatBytes(doc.size_bytes)}</span>·<span>{timeAgo(doc.created_at)}</span>
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {subject && <Badge tone="accent" title={doc.subject_suggested ? "Suggested automatically from the content" : undefined}>
          {subject.name}{doc.subject_suggested && " · suggested"}</Badge>}
        {!processing && doc.status !== "failed" && <Badge>{doc.page_count} {unit}</Badge>}
        {!processing && doc.image_count > 0 && <Badge>{doc.image_count} images</Badge>}
        {doc.status === "partial" && <Badge tone="warn">Partial</Badge>}
      </div>

      {processing && (
        <div className="mt-3" aria-live="polite">
          <div className="mb-1 flex justify-between text-xs"><span className="text-accent-soft">{PROCESSING_LABELS[doc.status]}</span><span className="text-ink-faint">{doc.progress}%</span></div>
          <ProgressBar value={doc.progress} />
          <div className="mt-1 truncate text-[11px] text-ink-faint">{doc.stage_message}</div>
        </div>
      )}
      {doc.status === "failed" && (
        <div className="mt-3 rounded-lg border border-rose-400/20 bg-rose-400/5 p-2 text-xs text-rose-200">
          <CircleAlert className="mr-1 inline h-3.5 w-3.5" />{doc.error_message || "Processing failed."}
        </div>
      )}
      {doc.warnings.length > 0 && !processing && (
        <details className="mt-2 text-[11px] text-amber-200/80">
          <summary className="cursor-pointer">{doc.warnings.length} processing note(s)</summary>
          <ul className="mt-1 list-disc space-y-0.5 pl-4">{doc.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
        </details>
      )}

      <div className="mt-auto flex items-center gap-1 pt-3">
        <select aria-label="Subject" className="input h-8 max-w-[150px] py-0 text-xs" value={doc.subject_id ?? ""}
          onChange={async (e) => { const v = e.target.value; await api.updateDocument(doc.id, v ? { subject_id: Number(v) } : { clear_subject: true }); onChanged(); }}>
          <option value="">No subject</option>
          {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <div className="ml-auto flex">
          {(doc.status === "failed" || doc.status === "partial") && (
            <Button size="icon" variant="ghost" title="Retry processing" onClick={async () => { await api.reprocess(doc.id); onChanged(); }}><RefreshCw className="h-4 w-4" /></Button>
          )}
          <Button size="icon" variant="ghost" title="Rename" onClick={() => setEditing(!editing)}><Pencil className="h-4 w-4" /></Button>
          <Button size="icon" variant="ghost" title="Delete" onClick={remove} disabled={busy}><Trash2 className="h-4 w-4" /></Button>
        </div>
      </div>
    </div>
  );
}
