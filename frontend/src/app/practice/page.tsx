"use client";

import { ClipboardCheck, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Badge, Button, Card, EmptyState, PageHeader, Segmented, Spinner } from "@/components/ui";
import { useAppStatus } from "@/hooks/useAppStatus";
import { useAsync } from "@/hooks/useAsync";
import { cn, timeAgo } from "@/lib/utils";
import { TYPE_LABELS } from "@/features/exams/constants";
import { api } from "@/services/api";
import type { QuestionType } from "@/types/api";


export default function PracticePage() {
  const router = useRouter();
  const { subjects } = useAppStatus();
  const docs = useAsync(() => api.documents(), []);
  const quizzes = useAsync(() => api.quizzes(), []);
  const [docIds, setDocIds] = useState<string[]>([]);
  const [subjectId, setSubjectId] = useState<number | null>(null);
  const [topic, setTopic] = useState("");
  const [difficulty, setDifficulty] = useState<"easy" | "medium" | "hard">("medium");
  const [count, setCount] = useState(10);
  const [types, setTypes] = useState<QuestionType[]>(["sba", "true_false"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready = (docs.data ?? []).filter((d) => d.status === "ready" || d.status === "partial")
    .filter((d) => !subjectId || d.subject_id === subjectId);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const q = await api.generateQuiz({ document_ids: docIds, subject_id: subjectId, topic: topic || null, difficulty,
        num_questions: count, question_types: types });
      router.push(`/practice/${q.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader title="Practice & Exams" icon={<ClipboardCheck />}
        subtitle="Exam questions generated from your own documents, each linked to the page that supports the answer." />
      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="space-y-5 p-5 lg:col-span-3">
          <h2 className="section-title">Build an examination</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor="subj">Subject</label>
              <select id="subj" className="input" value={subjectId ?? ""} onChange={(e) => { setSubjectId(e.target.value ? Number(e.target.value) : null); setDocIds([]); }}>
                <option value="">Any subject</option>{subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="topic">Topic (optional)</label>
              <input id="topic" className="input" placeholder="e.g. cardiac conduction" value={topic} onChange={(e) => setTopic(e.target.value)} />
            </div>
          </div>
          <div>
            <label className="label">Documents {docIds.length ? `(${docIds.length} selected)` : "(all in scope)"}</label>
            <div className="flex max-h-36 flex-wrap gap-1.5 overflow-y-auto">
              {docs.loading && <Spinner className="h-4 w-4" />}
              {!docs.loading && ready.length === 0 && <span className="text-sm text-ink-faint">No processed documents in this scope. <Link href="/library" className="text-accent">Upload one</Link>.</span>}
              {ready.map((d) => (
                <button key={d.id} type="button" onClick={() => setDocIds(docIds.includes(d.id) ? docIds.filter((x) => x !== d.id) : [...docIds, d.id])}
                  className={cn("chip", docIds.includes(d.id) ? "border-accent/50 bg-accent/15 text-accent-soft" : "border-white/10 text-ink-muted hover:text-ink")}>{d.title}</button>
              ))}
            </div>
          </div>
          <div>
            <label className="label">Question types</label>
            <div className="flex flex-wrap gap-1.5">
              {(Object.keys(TYPE_LABELS) as QuestionType[]).map((t) => (
                <button key={t} type="button" aria-pressed={types.includes(t)}
                  onClick={() => setTypes(types.includes(t) ? types.filter((x) => x !== t) : [...types, t])}
                  className={cn("chip", types.includes(t) ? "border-accent/50 bg-accent/15 text-accent-soft" : "border-white/10 text-ink-muted hover:text-ink")}>{TYPE_LABELS[t]}</button>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap items-end gap-4">
            <div><label className="label">Difficulty</label>
              <Segmented value={difficulty} onChange={setDifficulty} options={[{ value: "easy", label: "Easy" }, { value: "medium", label: "Medium" }, { value: "hard", label: "Hard" }]} /></div>
            <div><label className="label" htmlFor="n">Questions</label>
              <input id="n" type="number" min={1} max={30} className="input w-24" value={count} onChange={(e) => setCount(Math.max(1, Math.min(30, Number(e.target.value))))} /></div>
            <Button variant="primary" className="ml-auto" onClick={generate} loading={busy} disabled={!types.length || ready.length === 0}>
              <Sparkles className="h-4 w-4" />{busy ? "Writing questions…" : "Start examination"}
            </Button>
          </div>
          {busy && <p className="text-xs text-ink-faint">Retrieving evidence and writing questions. This can take up to a minute.</p>}
          {error && <Alert tone="danger">{error}</Alert>}
        </Card>

        <Card className="p-5 lg:col-span-2">
          <h2 className="section-title mb-3">Previous examinations</h2>
          {quizzes.loading ? <Spinner /> : quizzes.data?.length === 0 ? (
            <EmptyState icon={<ClipboardCheck />} title="No exams yet">Your generated quizzes and scores will appear here.</EmptyState>
          ) : (
            <ul className="divide-y divide-white/5">
              {quizzes.data?.map((q) => (
                <li key={q.id} className="flex items-center gap-3 py-2.5">
                  <Link href={`/practice/${q.id}`} className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-ink hover:text-accent-soft">{q.title}</div>
                    <div className="text-[11px] text-ink-faint">{q.question_count} questions · {q.difficulty} · {timeAgo(q.created_at)}</div>
                  </Link>
                  {q.best_percent !== null ? <Badge tone={q.best_percent >= 70 ? "ok" : "warn"}>{q.best_percent}%</Badge> : <Badge>Not taken</Badge>}
                  <button aria-label="Delete quiz" className="text-ink-faint hover:text-rose-300" onClick={async () => { await api.deleteQuiz(q.id); quizzes.reload(true); }}><Trash2 className="h-3.5 w-3.5" /></button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
