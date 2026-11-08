"use client";

import { Flame, Layers, Plus, Quote, Repeat, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Button, Card, EmptyState, Modal, PageHeader, Spinner, Stat } from "@/components/ui";
import { useAppStatus } from "@/hooks/useAppStatus";
import { useAsync } from "@/hooks/useAsync";
import { cn, inDays, STATUS_META } from "@/lib/utils";
import { api } from "@/services/api";
import type { Flashcard } from "@/types/api";

const RATINGS = [
  { r: 0, label: "Again", hint: "<10 min", cls: "border-rose-400/40 text-rose-300 hover:bg-rose-400/10" },
  { r: 1, label: "Hard", hint: "", cls: "border-amber-400/40 text-amber-300 hover:bg-amber-400/10" },
  { r: 2, label: "Good", hint: "", cls: "border-accent/40 text-accent-soft hover:bg-accent/10" },
  { r: 3, label: "Easy", hint: "", cls: "border-emerald-400/40 text-emerald-300 hover:bg-emerald-400/10" },
];

function Reviewer({ cards, onDone }: { cards: Flashcard[]; onDone: () => void }) {
  const [i, setI] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [busy, setBusy] = useState(false);
  const card = cards[i];
  if (!card) return (
    <EmptyState icon={<Sparkles />} title="Session complete" action={<Button onClick={onDone}>Back to overview</Button>}>
      You reviewed {cards.length} card(s). They are rescheduled with spaced repetition.
    </EmptyState>
  );
  async function rate(r: number) {
    setBusy(true);
    try { await api.reviewCard(card.id, r); setFlipped(false); setI(i + 1); } finally { setBusy(false); }
  }
  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-2 flex justify-between text-xs text-ink-faint"><span>Card {i + 1} of {cards.length}</span>{card.topic && <span>{card.topic}</span>}</div>
      <button onClick={() => setFlipped(!flipped)} className="card block min-h-[260px] w-full p-8 text-left transition hover:border-accent/30" aria-label="Flip card">
        <div className="text-[11px] uppercase tracking-wider text-accent/80">{flipped ? "Answer" : "Question"}</div>
        <div className="mt-3 whitespace-pre-wrap text-lg text-white">{card.front}</div>
        {flipped && <div className="mt-5 whitespace-pre-wrap border-t border-white/10 pt-5 text-[0.97rem] text-ink">{card.back}</div>}
        {!flipped && <div className="mt-8 text-xs text-ink-faint">Click the card to reveal the answer</div>}
      </button>
      {flipped && card.citation && (
        <Link href={`/library/${card.citation.document_id}?page=${card.citation.page_number}`} className="mt-2 inline-flex items-center gap-1 text-xs text-accent-soft hover:underline">
          <Quote className="h-3 w-3" />{card.citation.document_title} · {card.citation.page_kind} {card.citation.page_number}</Link>
      )}
      {flipped ? (
        <div className="mt-4 grid grid-cols-4 gap-2">
          {RATINGS.map((x) => (
            <button key={x.r} disabled={busy} onClick={() => rate(x.r)} className={cn("rounded-xl border bg-navy-850 px-2 py-2.5 text-sm font-semibold transition", x.cls)}>{x.label}</button>
          ))}
        </div>
      ) : <Button className="mt-4 w-full justify-center" variant="primary" onClick={() => setFlipped(true)}>Show answer</Button>}
    </div>
  );
}

export default function RevisionPage() {
  const { subjects } = useAppStatus();
  const rev = useAsync(() => api.revision(), []);
  const all = useAsync(() => api.cards(), []);
  const docs = useAsync(() => api.documents(), []);
  const [reviewing, setReviewing] = useState<Flashcard[] | null>(null);
  const [genOpen, setGenOpen] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [docIds, setDocIds] = useState<string[]>([]);
  const [subjectId, setSubjectId] = useState<number | null>(null);
  const [topic, setTopic] = useState("");
  const [count, setCount] = useState(10);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "info" | "danger"; text: string } | null>(null);
  const [front, setFront] = useState("");
  const [back, setBack] = useState("");

  const reload = () => { rev.reload(true); all.reload(true); };
  if (reviewing) return <Reviewer cards={reviewing} onDone={() => { setReviewing(null); reload(); }} />;
  const ready = (docs.data ?? []).filter((d) => d.status === "ready" || d.status === "partial");

  async function generate() {
    setBusy(true); setMsg(null);
    try {
      const r = await api.generateCards({ document_ids: docIds, subject_id: subjectId, topic: topic || null, count });
      setMsg({ tone: "info", text: `Created ${r.cards.length} flashcard(s) with ${r.provider === "anthropic" ? "Claude" : "a local model"} (${r.model}).${r.warnings.length ? ` ${r.warnings.length} rejected for lacking source support.` : ""}` });
      setGenOpen(false); reload();
    } catch (e) { setMsg({ tone: "danger", text: (e as Error).message }); } finally { setBusy(false); }
  }

  const s = rev.data?.stats;
  return (
    <div>
      <PageHeader title="Revision Centre" icon={<Repeat />} subtitle="Spaced-repetition flashcards built from your documents and your quiz mistakes."
        actions={<>
          <Button onClick={() => setManualOpen(true)}><Plus className="h-4 w-4" />New card</Button>
          <Button variant="outline" onClick={() => setGenOpen(true)}><Sparkles className="h-4 w-4" />Generate from documents</Button>
        </>} />
      {msg && <Alert tone={msg.tone} className="mb-4" onClose={() => setMsg(null)}>{msg.text}</Alert>}
      {rev.loading ? <Spinner /> : s && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Due now" value={s.due_now} icon={<Flame className="h-4 w-4 text-amber-300" />} />
            <Stat label="Due in 24 h" value={s.due_within_24h} />
            <Stat label="Reviewed today" value={s.reviewed_today} />
            <Stat label="Total cards" value={s.total} hint={`${s.mature} mature (21+ days)`} icon={<Layers className="h-4 w-4" />} />
          </div>
          <Card className="mt-5 flex flex-col items-start gap-3 p-5 sm:flex-row sm:items-center">
            <div className="flex-1">
              <h2 className="font-semibold text-white">Daily revision</h2>
              <p className="text-sm text-ink-muted">{s.due_now ? `${s.due_now} card(s) are due. Short daily sessions beat cramming.` : "Nothing is due right now — great work."}</p>
            </div>
            <Button variant="primary" disabled={!rev.data?.due.length} onClick={() => setReviewing(rev.data!.due)}>Start review ({rev.data?.due.length ?? 0})</Button>
          </Card>
          {rev.data!.weak_topics.length > 0 && (
            <Card className="mt-5 p-5">
              <h2 className="section-title mb-3">Weak topics</h2>
              <div className="flex flex-wrap gap-2">
                {rev.data!.weak_topics.map((t) => (
                  <Link key={t.id} href={`/tutor?q=${encodeURIComponent(`Explain ${t.name} simply, then test me on it.`)}`}
                    className={cn("chip hover:brightness-125", STATUS_META[t.status].color)}>{t.name} · {t.questions_correct}/{t.questions_answered}</Link>
                ))}
              </div>
            </Card>
          )}
        </>
      )}

      <Card className="mt-5 p-5">
        <h2 className="section-title mb-3">All flashcards</h2>
        {all.data?.length === 0 ? <p className="text-sm text-ink-muted">No flashcards yet. Generate some from a document, or take a quiz — mistakes become cards.</p> : (
          <ul className="divide-y divide-white/5">
            {all.data?.map((c) => (
              <li key={c.id} className="flex items-start gap-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <div className="line-clamp-1 text-sm text-ink">{c.front}</div>
                  <div className="line-clamp-1 text-xs text-ink-faint">{c.back}</div>
                </div>
                <Badge tone={c.origin === "quiz_mistake" ? "warn" : c.origin === "manual" ? "default" : "violet"}>{c.origin === "quiz_mistake" ? "From mistake" : c.origin === "manual" ? "Manual" : "AI"}</Badge>
                <span className="w-20 text-right text-[11px] text-ink-faint">{c.suspended ? "suspended" : inDays(c.due_at)}</span>
                <button aria-label="Delete card" className="text-ink-faint hover:text-rose-300" onClick={async () => { await api.deleteCard(c.id); reload(); }}><Trash2 className="h-3.5 w-3.5" /></button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Modal open={genOpen} onClose={() => setGenOpen(false)} title="Generate flashcards">
        <div className="space-y-4">
          <div><label className="label">Subject</label>
            <select className="input" value={subjectId ?? ""} onChange={(e) => setSubjectId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">Any</option>{subjects.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></div>
          <div><label className="label">Documents</label>
            <div className="flex max-h-32 flex-wrap gap-1.5 overflow-y-auto">{ready.map((d) => (
              <button key={d.id} onClick={() => setDocIds(docIds.includes(d.id) ? docIds.filter((x) => x !== d.id) : [...docIds, d.id])}
                className={cn("chip", docIds.includes(d.id) ? "border-accent/50 bg-accent/15 text-accent-soft" : "border-white/10 text-ink-muted")}>{d.title}</button>))}</div></div>
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2"><label className="label">Topic (optional)</label><input className="input" value={topic} onChange={(e) => setTopic(e.target.value)} /></div>
            <div><label className="label">Cards</label><input type="number" min={1} max={50} className="input" value={count} onChange={(e) => setCount(Number(e.target.value))} /></div>
          </div>
          <Button variant="primary" className="w-full justify-center" onClick={generate} loading={busy}>Generate</Button>
        </div>
      </Modal>
      <Modal open={manualOpen} onClose={() => setManualOpen(false)} title="New flashcard">
        <form className="space-y-3" onSubmit={async (e) => { e.preventDefault(); await api.createCard({ front, back }); setFront(""); setBack(""); setManualOpen(false); reload(); }}>
          <div><label className="label">Front</label><textarea required className="input" value={front} onChange={(e) => setFront(e.target.value)} /></div>
          <div><label className="label">Back</label><textarea required className="input" value={back} onChange={(e) => setBack(e.target.value)} /></div>
          <Button variant="primary" type="submit">Save card</Button>
        </form>
      </Modal>
    </div>
  );
}
