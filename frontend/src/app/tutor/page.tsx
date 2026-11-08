"use client";

import { Bot, History, Plus, Trash2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Button, Card, Spinner } from "@/components/ui";
import { ChatView } from "@/features/tutor/ChatView";
import { useAppStatus } from "@/hooks/useAppStatus";
import { useAsync } from "@/hooks/useAsync";
import { cn, timeAgo } from "@/lib/utils";
import { api } from "@/services/api";
import type { Source } from "@/types/api";

function TutorInner() {
  const params = useSearchParams();
  const router = useRouter();
  const { subjects } = useAppStatus();
  const convs = useAsync(() => api.conversations(), []);
  const docs = useAsync(() => api.documents({ status: "" }), []);
  const [conversationId, setConversationId] = useState<string | null>(params.get("conversation"));
  const [chatKey, setChatKey] = useState(0);
  const [scope, setScope] = useState<"all" | "docs" | "subject">("all");
  const [docIds, setDocIds] = useState<string[]>([]);
  const [subjectId, setSubjectId] = useState<number | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const ready = (docs.data ?? []).filter((d) => d.status === "ready" || d.status === "partial");

  const open = (id: string | null) => { setConversationId(id); setChatKey((k) => k + 1); setShowHistory(false); };
  const onCite = (s: Source) => s.document_id && router.push(`/library/${s.document_id}?page=${s.page_number}`);

  return (
    <div className="flex h-[calc(100vh-3.5rem-4rem)] gap-4 lg:h-[calc(100vh-3.5rem-4rem)]">
      <aside className={cn("card w-72 shrink-0 flex-col overflow-hidden", showHistory ? "fixed inset-x-4 top-20 z-30 flex max-h-[70vh] w-auto" : "hidden lg:flex")}>
        <div className="flex items-center justify-between border-b border-white/5 p-3">
          <span className="section-title">Conversations</span>
          <Button size="sm" variant="outline" onClick={() => open(null)}><Plus className="h-3.5 w-3.5" />New</Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {convs.loading && <div className="flex justify-center p-4"><Spinner /></div>}
          {convs.data?.length === 0 && <p className="p-3 text-xs text-ink-faint">No conversations yet.</p>}
          {convs.data?.map((c) => (
            <div key={c.id} className={cn("group flex items-start gap-2 rounded-lg px-2.5 py-2 transition hover:bg-white/5",
              c.id === conversationId && "bg-accent/10")}>
              <button className="min-w-0 flex-1 text-left" onClick={() => open(c.id)}>
                <div className="truncate text-sm text-ink">{c.title}</div>
                <div className="text-[11px] text-ink-faint">{timeAgo(c.updated_at)} · {c.message_count} messages · L{c.teaching_level}</div>
              </button>
              <button aria-label="Delete conversation" className="opacity-0 transition group-hover:opacity-100 text-ink-faint hover:text-rose-300"
                onClick={async () => { await api.deleteConversation(c.id); if (c.id === conversationId) open(null); convs.reload(true); }}>
                <Trash2 className="h-3.5 w-3.5" /></button>
            </div>
          ))}
        </div>
      </aside>

      <Card className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-white/5 px-4 py-2.5">
          <Bot className="h-5 w-5 text-accent" />
          <h1 className="font-semibold text-white">AI Medical Tutor</h1>
          <Button size="sm" variant="ghost" className="lg:hidden" onClick={() => setShowHistory(!showHistory)}><History className="h-4 w-4" />History</Button>
          {!conversationId && (
            <div className="ml-auto flex flex-wrap items-center gap-2 text-xs">
              <span className="text-ink-faint">Search in</span>
              <select className="input h-8 w-auto py-0 text-xs" value={scope} onChange={(e) => setScope(e.target.value as typeof scope)} aria-label="Scope">
                <option value="all">All my documents</option><option value="docs">Selected documents</option><option value="subject">A subject</option>
              </select>
              {scope === "subject" && (
                <select className="input h-8 w-auto py-0 text-xs" value={subjectId ?? ""} onChange={(e) => setSubjectId(e.target.value ? Number(e.target.value) : null)} aria-label="Subject">
                  <option value="">Choose…</option>{subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              )}
            </div>
          )}
        </div>
        {scope === "docs" && !conversationId && (
          <div className="flex max-h-28 flex-wrap gap-1.5 overflow-y-auto border-b border-white/5 px-4 py-2">
            {ready.length === 0 && <span className="text-xs text-ink-faint">No processed documents yet.</span>}
            {ready.map((d) => (
              <button key={d.id} onClick={() => setDocIds(docIds.includes(d.id) ? docIds.filter((x) => x !== d.id) : [...docIds, d.id])}
                className={cn("chip", docIds.includes(d.id) ? "border-accent/50 bg-accent/15 text-accent-soft" : "border-white/10 text-ink-muted")}>{d.title}</button>
            ))}
          </div>
        )}
        <div className="min-h-0 flex-1">
          <ChatView key={chatKey} conversationId={conversationId} initialPrompt={params.get("q")}
            documentIds={scope === "docs" ? docIds : []} subjectId={scope === "subject" ? subjectId : null}
            onConversation={(id) => { setConversationId(id); convs.reload(true); }} onCite={onCite} />
        </div>
      </Card>
    </div>
  );
}

export default function TutorPage() {
  return <Suspense fallback={<Spinner />}><TutorInner /></Suspense>;
}
