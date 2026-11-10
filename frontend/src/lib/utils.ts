export function cn(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  const s = Math.round((Date.now() - d.getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} d ago`;
  return d.toLocaleDateString();
}

export function inDays(iso: string): string {
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  const h = (d.getTime() - Date.now()) / 3600000;
  if (h <= 0) return "due now";
  if (h < 1) return `in ${Math.max(1, Math.round(h * 60))} min`;
  if (h < 24) return `in ${Math.round(h)} h`;
  return `in ${Math.round(h / 24)} d`;
}

export const LEVELS = [
  { level: 1, name: "Beginner", long: "Absolute beginner" },
  { level: 2, name: "Med student", long: "Medical student" },
  { level: 3, name: "Advanced", long: "Advanced" },
  { level: 4, name: "Clinical", long: "Clinical correlation" },
  { level: 5, name: "Exam prep", long: "Examination preparation" },
];

export const STATUS_META: Record<string, { label: string; color: string }> = {
  not_studied: { label: "Not studied", color: "text-ink-faint border-white/10 bg-white/5" },
  learning: { label: "Learning", color: "text-sky-300 border-sky-400/30 bg-sky-400/10" },
  needs_revision: { label: "Needs revision", color: "text-amber-300 border-amber-400/30 bg-amber-400/10" },
  understood: { label: "Understood", color: "text-teal-300 border-teal-400/30 bg-teal-400/10" },
  mastered: { label: "Mastered", color: "text-emerald-300 border-emerald-400/30 bg-emerald-400/10" },
};

export const PROCESSING_LABELS: Record<string, string> = {
  uploaded: "Uploaded", validating: "Validating", stored: "Queued", extracting: "Extracting", ocr: "Running OCR",
  analysing_images: "Analysing images", chunking: "Chunking", embedding: "Embedding", indexing: "Indexing",
  ready: "Ready", partial: "Ready (with warnings)", failed: "Failed",
};

export const isProcessing = (s: string) => !["ready", "partial", "failed"].includes(s);
