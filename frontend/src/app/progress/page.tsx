"use client";

import { ChartLine } from "lucide-react";
import Link from "next/link";

import { Alert, Badge, Card, EmptyState, PageHeader, ProgressBar, Spinner, Stat } from "@/components/ui";
import { useAsync } from "@/hooks/useAsync";
import { cn, STATUS_META, timeAgo } from "@/lib/utils";
import { api } from "@/services/api";
import type { TopicStatus } from "@/types/api";

const ORDER: TopicStatus[] = ["not_studied", "learning", "needs_revision", "understood", "mastered"];
const BAR: Record<TopicStatus, string> = { not_studied: "bg-slate-500", learning: "bg-sky-400", needs_revision: "bg-amber-400",
  understood: "bg-teal-400", mastered: "bg-emerald-400" };

export default function ProgressPage() {
  const p = useAsync(() => api.progress(), []);
  if (p.error) return <Alert tone="danger">{p.error.message}</Alert>;
  if (!p.data) return <div className="flex justify-center py-12"><Spinner /></div>;
  const d = p.data;
  const totalTopics = ORDER.reduce((a, s) => a + d.topic_status[s], 0);
  const maxAct = Math.max(1, ...d.activity_30d.map((x) => x.activities));
  const hist = d.quiz_history;

  return (
    <div>
      <PageHeader title="Progress Analytics" icon={<ChartLine />} subtitle={d.disclaimer} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Documents" value={d.totals.documents} />
        <Stat label="Tutor conversations" value={d.totals.conversations} />
        <Stat label="Quiz attempts" value={d.totals.quiz_attempts} />
        <Stat label="Flashcards due" value={d.revision.due_now} hint={`${d.revision.total} total`} />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="section-title mb-4">Topic status</h2>
          {totalTopics === 0 ? <p className="text-sm text-ink-muted">Topics appear once you take quizzes, review flashcards or add topics in Subjects.</p> : (
            <>
              <div className="flex h-3 overflow-hidden rounded-full bg-white/5">
                {ORDER.map((s) => d.topic_status[s] > 0 && <div key={s} className={BAR[s]} style={{ width: `${(100 * d.topic_status[s]) / totalTopics}%` }} title={`${STATUS_META[s].label}: ${d.topic_status[s]}`} />)}
              </div>
              <div className="mt-3 flex flex-wrap gap-3 text-xs">
                {ORDER.map((s) => <span key={s} className="flex items-center gap-1.5 text-ink-muted"><span className={cn("h-2 w-2 rounded-full", BAR[s])} />{STATUS_META[s].label} {d.topic_status[s]}</span>)}
              </div>
            </>
          )}
        </Card>
        <Card className="p-5">
          <h2 className="section-title mb-4">Study activity · last 30 days</h2>
          <div className="flex h-28 items-end gap-[3px]" role="img" aria-label="Daily study activity bar chart">
            {d.activity_30d.map((x) => (
              <div key={x.date} className="group relative flex-1">
                <div className={cn("w-full rounded-t", x.activities ? "bg-gradient-to-t from-cyan-500/60 to-teal-300" : "bg-white/5")}
                  style={{ height: `${x.activities ? Math.max(6, (100 * x.activities) / maxAct) : 4}%`, minHeight: 3 }} />
                <div className="pointer-events-none absolute bottom-full left-1/2 mb-1 hidden -translate-x-1/2 whitespace-nowrap rounded bg-navy-700 px-1.5 py-0.5 text-[10px] group-hover:block">{x.date}: {x.activities}</div>
              </div>
            ))}
          </div>
          <div className="mt-1 flex justify-between text-[10px] text-ink-faint"><span>{d.activity_30d[0]?.date}</span><span>today</span></div>
        </Card>
        <Card className="p-5">
          <h2 className="section-title mb-4">Quiz scores</h2>
          {hist.length === 0 ? <p className="text-sm text-ink-muted">No quizzes taken yet.</p> : (
            <svg viewBox="0 0 300 110" className="w-full" role="img" aria-label="Quiz score history">
              {[0, 50, 100].map((y) => <line key={y} x1="0" x2="300" y1={100 - y} y2={100 - y} stroke="rgba(255,255,255,0.06)" />)}
              <polyline fill="none" stroke="#22d3ee" strokeWidth="2" points={hist.map((h, i) => `${hist.length === 1 ? 150 : (i * 290) / (hist.length - 1) + 5},${100 - h.percent}`).join(" ")} />
              {hist.map((h, i) => <circle key={i} cx={hist.length === 1 ? 150 : (i * 290) / (hist.length - 1) + 5} cy={100 - h.percent} r="3" fill="#67e8f9"><title>{`${Math.round(h.percent)}% · ${new Date(h.submitted_at).toLocaleDateString()}`}</title></circle>)}
            </svg>
          )}
        </Card>
        <Card className="p-5">
          <h2 className="section-title mb-4">Accuracy by subject</h2>
          {d.subjects.length === 0 ? <p className="text-sm text-ink-muted">No graded answers yet.</p> : (
            <div className="space-y-3">{d.subjects.map((s) => (
              <div key={s.subject}><div className="mb-1 flex justify-between text-xs"><span className="text-ink">{s.subject}</span>
                <span className="text-ink-faint">{s.accuracy === null ? "—" : `${s.accuracy}%`} · {s.answered} answered</span></div>
                <ProgressBar value={s.accuracy ?? 0} tone={(s.accuracy ?? 100) < 60 ? "warn" : "accent"} /></div>
            ))}</div>
          )}
        </Card>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="section-title mb-3">Topics</h2>
          {d.topics.length === 0 ? <EmptyState icon={<ChartLine />} title="No topics tracked yet" /> : (
            <ul className="divide-y divide-white/5">{d.topics.map((t) => (
              <li key={t.id} className="flex items-center gap-2 py-2 text-sm">
                <span className="min-w-0 flex-1 truncate text-ink">{t.name}</span>
                <span className="text-[11px] text-ink-faint">{t.questions_answered ? `${t.questions_correct}/${t.questions_answered}` : ""}</span>
                <span className={cn("chip", STATUS_META[t.status].color)}>{STATUS_META[t.status].label}</span>
              </li>))}</ul>
          )}
        </Card>
        <Card className="p-5">
          <h2 className="section-title mb-3">Study history</h2>
          {d.recent_sessions.length === 0 ? <p className="text-sm text-ink-muted">No study sessions yet.</p> : (
            <ul className="divide-y divide-white/5">{d.recent_sessions.map((s) => (
              <li key={s.id} className="flex items-center gap-2 py-2 text-sm">
                <Badge>{s.kind}</Badge>
                {s.document_id ? <Link href={`/library/${s.document_id}`} className="min-w-0 flex-1 truncate text-ink hover:text-accent-soft">{s.title}</Link>
                  : s.quiz_id ? <Link href={`/practice/${s.quiz_id}`} className="min-w-0 flex-1 truncate text-ink hover:text-accent-soft">{s.title}</Link>
                    : <span className="min-w-0 flex-1 truncate text-ink">{s.title}</span>}
                <span className="text-[11px] text-ink-faint">{s.activity_count}× · {timeAgo(s.last_activity_at)}</span>
              </li>))}</ul>
          )}
        </Card>
      </div>
    </div>
  );
}
