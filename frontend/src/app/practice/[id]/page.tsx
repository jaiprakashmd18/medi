"use client";

import { ChevronLeft, CircleCheckBig, CircleX, Clock, Quote, RotateCcw, Target } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Alert, Badge, Button, Card, ProgressBar, Spinner } from "@/components/ui";
import { TYPE_LABELS } from "@/features/exams/constants";
import { Markdown } from "@/features/tutor/Markdown";
import { useAsync } from "@/hooks/useAsync";
import { cn } from "@/lib/utils";
import { api, assetUrl } from "@/services/api";
import type { Attempt, QuestionPublic, QuestionResult } from "@/types/api";

const L = (i: number) => String.fromCharCode(65 + i);

function QuestionInput({ q, value, onChange }: { q: QuestionPublic; value: unknown; onChange: (v: unknown) => void }) {
  if (q.type === "sba" || q.type === "diagram")
    return (
      <div className="space-y-2" role="radiogroup">
        {q.options.map((o, i) => (
          <label key={i} className={cn("flex cursor-pointer items-start gap-3 rounded-xl border px-3.5 py-2.5 text-sm transition",
            value === i ? "border-accent/60 bg-accent/10 text-white" : "border-white/10 hover:border-white/20")}>
            <input type="radio" name={`q${q.index}`} checked={value === i} onChange={() => onChange(i)} className="mt-0.5 accent-cyan-400" />
            <span><span className="mr-2 font-semibold text-accent-soft">{L(i)}.</span>{o}</span>
          </label>
        ))}
      </div>
    );
  if (q.type === "multi") {
    const sel = (value as number[] | undefined) ?? [];
    return (
      <div className="space-y-2">
        {q.options.map((o, i) => (
          <label key={i} className={cn("flex cursor-pointer items-start gap-3 rounded-xl border px-3.5 py-2.5 text-sm transition",
            sel.includes(i) ? "border-accent/60 bg-accent/10 text-white" : "border-white/10 hover:border-white/20")}>
            <input type="checkbox" checked={sel.includes(i)} className="mt-0.5 accent-cyan-400"
              onChange={() => onChange(sel.includes(i) ? sel.filter((x) => x !== i) : [...sel, i])} />
            <span><span className="mr-2 font-semibold text-accent-soft">{L(i)}.</span>{o}</span>
          </label>
        ))}
      </div>
    );
  }
  if (q.type === "true_false")
    return (
      <div className="flex gap-2">
        {[true, false].map((v) => (
          <Button key={String(v)} variant={value === v ? "outline" : "secondary"} onClick={() => onChange(v)}>{v ? "True" : "False"}</Button>
        ))}
      </div>
    );
  if (q.type === "fill_blank")
    return <input className="input max-w-md" placeholder="Your answer" value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} aria-label="Answer" />;
  return <textarea className="input min-h-[120px]" placeholder={q.type === "viva" ? "Answer as you would speak to the examiner…" : "Write your answer…"}
    value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} aria-label="Answer" />;
}

function answerText(r: QuestionResult, options: string[]): string {
  const ca = r.correct_answer;
  if (Array.isArray(ca) && typeof ca[0] === "number") return (ca as number[]).map((i) => `${L(i)}. ${options[i]}`).join("; ");
  if (typeof ca === "boolean") return ca ? "True" : "False";
  if (Array.isArray(ca)) return (ca as string[]).join(" / ");
  return r.model_answer;
}

function yourAnswer(r: QuestionResult, options: string[]): string {
  const a = r.answer;
  if (a === null || a === undefined || a === "" || (Array.isArray(a) && !a.length)) return "No answer";
  if (typeof a === "number") return `${L(a)}. ${options[a] ?? ""}`;
  if (Array.isArray(a)) return (a as number[]).map((i) => `${L(i)}. ${options[i]}`).join("; ");
  if (typeof a === "boolean") return a ? "True" : "False";
  return String(a);
}

function Results({ attempt, questions, onRetry }: { attempt: Attempt; questions: QuestionPublic[]; onRetry: () => void }) {
  return (
    <div className="space-y-5">
      <Card className="p-6">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
          <div className="relative grid h-28 w-28 shrink-0 place-items-center rounded-full"
            style={{ background: `conic-gradient(#22d3ee ${attempt.percent * 3.6}deg, rgba(255,255,255,0.06) 0deg)` }}>
            <div className="grid h-[100px] w-[100px] place-items-center rounded-full bg-navy-900">
              <div className="text-center"><div className="text-2xl font-bold text-white">{Math.round(attempt.percent)}%</div>
                <div className="text-[11px] text-ink-faint">{attempt.score} / {attempt.max_score}</div></div>
            </div>
          </div>
          <div className="flex-1 space-y-3">
            <h2 className="text-lg font-semibold text-white">Results</h2>
            <div className="grid gap-2 sm:grid-cols-2">
              {attempt.topic_breakdown.map((t) => (
                <div key={t.topic}>
                  <div className="mb-1 flex justify-between text-xs"><span className={t.weak ? "text-amber-300" : "text-ink"}>{t.topic}</span><span className="text-ink-faint">{t.percent}%</span></div>
                  <ProgressBar value={t.percent} tone={t.weak ? "warn" : "accent"} />
                </div>
              ))}
            </div>
          </div>
        </div>
        {attempt.weak_topics.length > 0 && (
          <div className="mt-5 rounded-xl border border-amber-400/20 bg-amber-400/[0.05] p-3 text-sm">
            <div className="mb-1 flex items-center gap-1.5 font-semibold text-amber-200"><Target className="h-4 w-4" /> Weak areas</div>
            <div className="text-amber-100/90">{attempt.weak_topics.join(", ")}</div>
          </div>
        )}
        <ul className="mt-4 space-y-1 text-sm text-ink-muted">{attempt.recommendations.map((r, i) => <li key={i}>• {r}</li>)}</ul>
        <p className="mt-3 text-[11px] text-ink-faint">Scores measure recall of your study material, not clinical competence. Incorrect answers were added to your flashcards.</p>
        <div className="mt-4 flex gap-2"><Button onClick={onRetry}><RotateCcw className="h-4 w-4" />Retake</Button>
          <Link href="/revision"><Button variant="outline">Review flashcards</Button></Link></div>
      </Card>

      {attempt.results.map((r) => {
        const q = questions.find((x) => x.index === r.question_index);
        if (!q) return null;
        const partial = !r.correct && r.score > 0;
        return (
          <Card key={r.question_index} className={cn("p-5", r.correct ? "border-emerald-400/20" : partial ? "border-amber-400/20" : "border-rose-400/20")}>
            <div className="mb-2 flex flex-wrap items-center gap-1.5">
              {r.correct ? <CircleCheckBig className="h-5 w-5 text-emerald-400" /> : <CircleX className={cn("h-5 w-5", partial ? "text-amber-300" : "text-rose-400")} />}
              <span className="text-sm font-semibold text-white">Question {r.question_index + 1}</span>
              <Badge>{TYPE_LABELS[r.type]}</Badge>
              {r.topic && <Badge tone="accent">{r.topic}</Badge>}
              <Badge tone={r.grading === "keyword_estimate" ? "warn" : "default"}>
                {r.grading === "auto" ? "Auto-marked" : r.grading === "ai" ? "AI-marked" : r.grading === "keyword_estimate" ? "Estimated score" : "Unanswered"} · {Math.round(r.score * 100)}%
              </Badge>
            </div>
            <p className="text-sm text-ink">{q.prompt}</p>
            <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
              <div className="rounded-lg bg-white/[0.03] p-2.5"><div className="text-[11px] uppercase tracking-wider text-ink-faint">Your answer</div><div className="mt-0.5 whitespace-pre-wrap">{yourAnswer(r, q.options)}</div></div>
              <div className="rounded-lg bg-emerald-400/[0.05] p-2.5"><div className="text-[11px] uppercase tracking-wider text-emerald-300/80">{["short", "long", "viva"].includes(r.type) ? "Model answer" : "Correct answer"}</div>
                <div className="mt-0.5 whitespace-pre-wrap">{answerText(r, q.options)}</div></div>
            </div>
            {r.feedback && <p className="mt-2 text-sm text-ink-muted">{r.feedback}</p>}
            {r.missing_points && r.missing_points.length > 0 && <p className="mt-1 text-xs text-amber-200/80">Missing: {r.missing_points.join("; ")}</p>}
            {r.explanation && <div className="mt-3 border-t border-white/5 pt-3"><Markdown content={r.explanation}
              sources={r.citations.map((c, i) => ({ ...c, label: i + 1 }))}
              onCite={(c) => c.document_id && window.location.assign(`/library/${c.document_id}?page=${c.page_number}`)} /></div>}
            {r.citations.length > 0 && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-ink-faint"><Quote className="h-3 w-3" /> Supported by:
                {r.citations.map((c, i) => (
                  <Link key={i} href={`/library/${c.document_id}?page=${c.page_number}`} className="chip border-accent/30 text-accent-soft hover:bg-accent/10" title={c.snippet}>
                    {c.document_title} · {c.page_kind} {c.page_number}</Link>
                ))}
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}

export default function QuizRunner() {
  const { id } = useParams<{ id: string }>();
  const quiz = useAsync(() => api.quiz(id), [id]);
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(Date.now());
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => { const t = setInterval(() => setElapsed(Math.round((Date.now() - started.current) / 1000)), 1000); return () => clearInterval(t); }, []);

  if (quiz.error) return <Alert tone="danger">{quiz.error.message}</Alert>;
  if (!quiz.data) return <div className="flex justify-center py-12"><Spinner /></div>;
  const q = quiz.data;
  const answered = Object.values(answers).filter((v) => v !== undefined && v !== "" && !(Array.isArray(v) && !v.length)).length;

  async function submit() {
    if (answered < q.questions.length && !confirm(`${q.questions.length - answered} question(s) unanswered. Submit anyway?`)) return;
    setBusy(true);
    setError(null);
    try {
      setAttempt(await api.submitQuiz(id, answers, Math.round((Date.now() - started.current) / 1000)));
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <Link href="/practice" className="mb-3 inline-flex items-center gap-1 text-sm text-ink-muted hover:text-accent"><ChevronLeft className="h-4 w-4" />Practice & Exams</Link>
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-xl font-semibold text-white">{q.title}</h1>
        <Badge>{q.difficulty}</Badge>
        {q.model && <Badge tone={q.provider === "anthropic" ? "accent" : "info"}>Written by {q.provider === "anthropic" ? "Claude" : "local model"} · {q.model}</Badge>}
        {!attempt && <Badge><Clock className="h-3 w-3" />{Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}</Badge>}
      </div>
      {q.warnings.length > 0 && !attempt && (
        <details className="mb-4 text-xs text-ink-faint"><summary className="cursor-pointer">Quality checks rejected {q.warnings.filter((w) => w.startsWith("Rejected")).length} generated question(s)</summary>
          <ul className="mt-1 list-disc pl-5">{q.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></details>
      )}
      {attempt ? (
        <Results attempt={attempt} questions={q.questions} onRetry={() => { setAttempt(null); setAnswers({}); started.current = Date.now(); }} />
      ) : (
        <div className="space-y-4">
          {q.questions.map((qq) => (
            <Card key={qq.index} className="p-5">
              <div className="mb-3 flex flex-wrap items-center gap-1.5">
                <span className="grid h-7 w-7 place-items-center rounded-lg bg-accent/10 text-sm font-semibold text-accent">{qq.index + 1}</span>
                <Badge>{TYPE_LABELS[qq.type]}</Badge>
                {qq.topic && <Badge tone="accent">{qq.topic}</Badge>}
              </div>
              {qq.image_url && (
                <div className="mb-3"><Badge tone="ok">Original source diagram</Badge>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={assetUrl(qq.image_url)} alt="Diagram for this question" className="mt-2 max-h-72 rounded-lg bg-white" /></div>
              )}
              <p className="mb-4 whitespace-pre-wrap text-[0.95rem] text-white">{qq.prompt}</p>
              <QuestionInput q={qq} value={answers[String(qq.index)]} onChange={(v) => setAnswers({ ...answers, [String(qq.index)]: v })} />
            </Card>
          ))}
          {error && <Alert tone="danger">{error}</Alert>}
          <div className="sticky bottom-4 flex items-center gap-3 rounded-2xl border border-white/10 bg-navy-900/95 p-3 backdrop-blur">
            <div className="flex-1"><ProgressBar value={(100 * answered) / q.questions.length} /><div className="mt-1 text-xs text-ink-faint">{answered} of {q.questions.length} answered</div></div>
            <Button variant="primary" onClick={submit} loading={busy}>Submit answers</Button>
          </div>
        </div>
      )}
    </div>
  );
}
