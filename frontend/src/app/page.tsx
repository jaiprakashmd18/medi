"use client";

import { ArrowRight, Bot, BookOpen, Flame, Library, Send, Sparkles, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Badge, Button, Card, EmptyState, ProgressBar, Spinner } from "@/components/ui";
import { FileIcon } from "@/features/library/DocumentCard";
import { useAppStatus } from "@/hooks/useAppStatus";
import { useAsync, usePolling } from "@/hooks/useAsync";
import { isProcessing, PROCESSING_LABELS, STATUS_META, timeAgo } from "@/lib/utils";
import { api } from "@/services/api";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export default function Dashboard() {
  const router = useRouter();
  const { subjects } = useAppStatus();
  const dash = useAsync(() => api.dashboard(), []);
  const [q, setQ] = useState("");
  usePolling(() => dash.reload(true), 2000, !!dash.data?.recent_documents.some((d) => isProcessing(d.status)));

  if (dash.error) return <Alert tone="danger">{dash.error.message}</Alert>;
  if (!dash.data) return <div className="flex justify-center py-16"><Spinner /></div>;
  const d = dash.data;
  const topicTotal = Object.values(d.topic_status).reduce((a, b) => a + (b ?? 0), 0);
  const empty = d.recent_documents.length === 0;

  return (
    <div className="space-y-6">
      <section className="card relative overflow-hidden p-6 lg:p-8">
        <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-accent/10 blur-3xl" />
        <div className="relative">
          <p className="text-sm text-accent-soft">{greeting()},</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-white lg:text-3xl">{d.user.display_name}</h1>
          <p className="mt-2 max-w-xl text-sm text-ink-muted">Upload your lecture notes and slides — your AI professor teaches from them, cites every page, and builds exams and revision around what you study.</p>
          <form className="mt-5 flex max-w-2xl gap-2" onSubmit={(e) => { e.preventDefault(); if (q.trim()) router.push(`/tutor?q=${encodeURIComponent(q)}`); }}>
            <div className="relative flex-1">
              <Bot className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-accent" />
              <input className="input h-11 pl-9" placeholder="Ask the AI tutor, e.g. “Teach me the brachial plexus”" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Ask the AI tutor" />
            </div>
            <Button type="submit" variant="primary" size="lg" disabled={!q.trim()}><Send className="h-4 w-4" /><span className="hidden sm:inline">Ask</span></Button>
          </form>
        </div>
      </section>

      {empty ? (
        <Card><EmptyState icon={<Upload />} title="Start by uploading a medical document"
          action={<Link href="/library"><Button variant="primary"><Upload className="h-4 w-4" />Upload to My Library</Button></Link>}>
          PDF, PowerPoint, Word or images. Text, tables and diagrams are extracted locally on your computer.
        </EmptyState></Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="p-5 lg:col-span-2">
            <div className="mb-3 flex items-center justify-between"><h2 className="section-title">Continue learning</h2></div>
            {d.continue_learning.length === 0 ? <p className="text-sm text-ink-muted">Open a document to start studying — your place is remembered.</p> : (
              <div className="grid gap-3 sm:grid-cols-3">
                {d.continue_learning.map((doc) => (
                  <Link key={doc.id} href={`/library/${doc.id}?page=${doc.last_page_viewed}`} className="card card-hover block p-4">
                    <FileIcon type={doc.file_type} className="h-5 w-5 text-accent" />
                    <div className="mt-2 line-clamp-2 text-sm font-medium text-white">{doc.title}</div>
                    <div className="mt-2 text-[11px] text-ink-faint">{doc.file_type === "pptx" ? "Slide" : "Page"} {doc.last_page_viewed} of {doc.page_count} · {timeAgo(doc.last_opened_at)}</div>
                    <ProgressBar value={(100 * doc.last_page_viewed) / Math.max(1, doc.page_count)} className="mt-2" />
                  </Link>
                ))}
              </div>
            )}
          </Card>
          <Card className="p-5">
            <h2 className="section-title mb-3">Revision due</h2>
            <div className="flex items-end gap-3">
              <div className="text-4xl font-bold text-white">{d.revision.due_now}</div>
              <div className="pb-1 text-sm text-ink-muted">cards due now<br /><span className="text-xs text-ink-faint">{d.revision.due_within_24h} within 24 h · {d.revision.reviewed_today} reviewed today</span></div>
            </div>
            <Link href="/revision"><Button className="mt-4 w-full justify-center" variant={d.revision.due_now ? "primary" : "secondary"}><Flame className="h-4 w-4" />Open Revision Centre</Button></Link>
          </Card>

          <Card className="p-5 lg:col-span-2">
            <div className="mb-3 flex items-center justify-between"><h2 className="section-title">Recently uploaded</h2>
              <Link href="/library" className="text-xs text-accent hover:underline">My Library <ArrowRight className="inline h-3 w-3" /></Link></div>
            <ul className="divide-y divide-white/5">
              {d.recent_documents.map((doc) => (
                <li key={doc.id}>
                  <Link href={`/library/${doc.id}`} className="flex items-center gap-3 py-2.5 hover:text-accent-soft">
                    <FileIcon type={doc.file_type} className="h-4 w-4 shrink-0 text-accent" />
                    <span className="min-w-0 flex-1 truncate text-sm text-ink">{doc.title}</span>
                    {isProcessing(doc.status) ? <Badge tone="info">{PROCESSING_LABELS[doc.status]} {doc.progress}%</Badge>
                      : doc.status === "failed" ? <Badge tone="danger">Failed</Badge>
                        : <span className="text-[11px] text-ink-faint">{doc.page_count} {doc.file_type === "pptx" ? "slides" : "pages"} · {timeAgo(doc.created_at)}</span>}
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
          <Card className="p-5">
            <h2 className="section-title mb-3">Learning progress</h2>
            {topicTotal === 0 ? <p className="text-sm text-ink-muted">Take a quiz or review flashcards to start tracking topics.</p> : (
              <div className="space-y-2">
                {Object.entries(STATUS_META).map(([k, v]) => {
                  const n = d.topic_status[k as keyof typeof d.topic_status] ?? 0;
                  return <div key={k} className="flex items-center gap-2 text-sm"><span className={`chip ${v.color}`}>{v.label}</span><span className="ml-auto text-ink">{n}</span></div>;
                })}
              </div>
            )}
            <Link href="/progress" className="mt-4 inline-block text-xs text-accent hover:underline">Progress analytics →</Link>
          </Card>

          <Card className="p-5 lg:col-span-2">
            <h2 className="section-title mb-3">Recent study sessions</h2>
            {d.recent_sessions.length === 0 && d.recent_conversations.length === 0 ? <p className="text-sm text-ink-muted">No study sessions yet.</p> : (
              <ul className="divide-y divide-white/5">
                {d.recent_conversations.map((c) => (
                  <li key={c.id}><Link href={c.document_id ? `/library/${c.document_id}?conversation=${c.id}` : `/tutor?conversation=${c.id}`} className="flex items-center gap-3 py-2.5">
                    <Bot className="h-4 w-4 text-accent" /><span className="min-w-0 flex-1 truncate text-sm text-ink hover:text-accent-soft">{c.title}</span>
                    <span className="text-[11px] text-ink-faint">{timeAgo(c.updated_at)}</span></Link></li>
                ))}
                {d.recent_sessions.filter((s) => s.kind !== "tutor").slice(0, 4).map((s) => (
                  <li key={s.id} className="flex items-center gap-3 py-2.5">
                    {s.kind === "reading" ? <BookOpen className="h-4 w-4 text-sky-300" /> : <Sparkles className="h-4 w-4 text-violet-300" />}
                    <span className="min-w-0 flex-1 truncate text-sm text-ink">{s.title}</span><Badge>{s.kind}</Badge>
                    <span className="text-[11px] text-ink-faint">{timeAgo(s.last_activity_at)}</span></li>
                ))}
              </ul>
            )}
          </Card>
          <Card className="p-5">
            <h2 className="section-title mb-3">Subjects</h2>
            <div className="flex flex-wrap gap-1.5">
              {subjects.filter((s) => d.subject_counts[String(s.id)]).map((s) => (
                <Link key={s.id} href="/subjects" className="chip border-white/10 text-ink hover:border-accent/40">
                  <span className="h-2 w-2 rounded-full" style={{ background: s.color }} />{s.name} · {d.subject_counts[String(s.id)]}</Link>
              ))}
              {Object.keys(d.subject_counts).length === 0 && <p className="text-sm text-ink-muted">Assign subjects to documents in <Link className="text-accent" href="/library"><Library className="inline h-3 w-3" /> My Library</Link>.</p>}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
