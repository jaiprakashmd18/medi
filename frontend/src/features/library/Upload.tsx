"use client";

import { CircleCheckBig, CircleX, FileText, Upload } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { Alert, Button, ProgressBar } from "@/components/ui";
import { useAppStatus } from "@/hooks/useAppStatus";
import { cn, formatBytes } from "@/lib/utils";
import { uploadDocuments } from "@/services/api";

const ACCEPT = ".pdf,.pptx,.docx,.jpg,.jpeg,.png";
const OK_EXT = ["pdf", "pptx", "docx", "jpg", "jpeg", "png"];

export function UploadDropzone({ onUploaded }: { onUploaded: () => void }) {
  const { subjects } = useAppStatus();
  const [drag, setDrag] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [subjectId, setSubjectId] = useState<number | null>(null);
  const [pct, setPct] = useState<number | null>(null);
  const [errors, setErrors] = useState<{ filename: string; message: string }[]>([]);
  const [done, setDone] = useState<number>(0);
  const input = useRef<HTMLInputElement>(null);

  const add = useCallback((list: FileList | null) => {
    if (!list) return;
    const arr = Array.from(list);
    const bad = arr.filter((f) => !OK_EXT.includes(f.name.split(".").pop()?.toLowerCase() ?? ""));
    setErrors(bad.map((f) => ({ filename: f.name, message: "Unsupported type (PDF, PPTX, DOCX, JPG, PNG only)" })));
    setFiles((cur) => [...cur, ...arr.filter((f) => !bad.includes(f))]);
    setDone(0);
  }, []);

  async function start() {
    if (!files.length) return;
    setPct(0);
    setErrors([]);
    try {
      const r = await uploadDocuments(files, subjectId, setPct);
      setErrors(r.errors);
      setDone(r.documents.length);
      setFiles([]);
      onUploaded();
    } catch (e) {
      const det = (e as any).details?.errors as { filename: string; message: string }[] | undefined;
      setErrors(det ?? [{ filename: "", message: (e as Error).message }]);
    } finally {
      setPct(null);
    }
  }

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); add(e.dataTransfer.files); }}
        onClick={() => input.current?.click()}
        role="button" tabIndex={0} aria-label="Upload documents"
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        className={cn("focus-ring flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition",
          drag ? "border-accent bg-accent/10" : "border-white/10 bg-navy-850/50 hover:border-accent/40 hover:bg-navy-850")}>
        <div className="mb-3 grid h-12 w-12 place-items-center rounded-2xl bg-accent/10 text-accent"><Upload /></div>
        <div className="font-medium text-white">Drop medical documents here, or click to browse</div>
        <div className="mt-1 text-xs text-ink-muted">PDF, PowerPoint (PPTX), Word (DOCX), JPG and PNG · multiple files supported</div>
        <input ref={input} type="file" multiple accept={ACCEPT} className="hidden" data-testid="file-input"
          onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
      </div>

      {files.length > 0 && (
        <div className="card space-y-3 p-4">
          <ul className="space-y-1.5">
            {files.map((f, i) => (
              <li key={i} className="flex items-center gap-2 text-sm">
                <FileText className="h-4 w-4 text-accent" />
                <span className="min-w-0 flex-1 truncate">{f.name}</span>
                <span className="text-xs text-ink-faint">{formatBytes(f.size)}</span>
                <button className="text-ink-faint hover:text-rose-300" aria-label={`Remove ${f.name}`} onClick={() => setFiles(files.filter((_, j) => j !== i))}><CircleX className="h-4 w-4" /></button>
              </li>
            ))}
          </ul>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <select className="input sm:max-w-xs" value={subjectId ?? ""} onChange={(e) => setSubjectId(e.target.value ? Number(e.target.value) : null)} aria-label="Subject">
              <option value="">Subject: auto-detect</option>
              {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <Button variant="primary" onClick={start} loading={pct !== null} className="sm:ml-auto">
              Upload {files.length} file{files.length > 1 ? "s" : ""}
            </Button>
          </div>
          {pct !== null && <div><ProgressBar value={pct} /><div className="mt-1 text-xs text-ink-muted">Uploading… {pct}%</div></div>}
        </div>
      )}
      {done > 0 && <Alert tone="info"><CircleCheckBig className="mr-1 inline h-4 w-4" />{done} document(s) uploaded — processing has started below.</Alert>}
      {errors.map((e, i) => <Alert key={i} tone="danger" title={e.filename || undefined}>{e.message}</Alert>)}
    </div>
  );
}
