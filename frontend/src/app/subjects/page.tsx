"use client";

import { BookMarked, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Button, Card, Modal, PageHeader, Spinner } from "@/components/ui";
import { FileIcon } from "@/features/library/DocumentCard";
import { useAppStatus } from "@/hooks/useAppStatus";
import { useAsync } from "@/hooks/useAsync";
import { cn, STATUS_META } from "@/lib/utils";
import { api } from "@/services/api";
import type { Subject, TopicStatus } from "@/types/api";

function SubjectDetail({ subject }: { subject: Subject }) {
  const docs = useAsync(() => api.documents({ subject_id: subject.id }), [subject.id]);
  const topics = useAsync(() => api.topics(subject.id), [subject.id]);
  const [name, setName] = useState("");
  return (
    <div className="space-y-5">
      <p className="text-sm text-ink-muted">{subject.description}</p>
      <div>
        <h3 className="section-title mb-2">Topics</h3>
        <form className="mb-3 flex gap-2" onSubmit={async (e) => { e.preventDefault(); if (!name.trim()) return; await api.createTopic({ name, subject_id: subject.id }); setName(""); topics.reload(true); }}>
          <input className="input" placeholder="Add a topic, e.g. Brachial plexus" value={name} onChange={(e) => setName(e.target.value)} />
          <Button type="submit"><Plus className="h-4 w-4" />Add</Button>
        </form>
        {topics.data?.length === 0 && <p className="text-sm text-ink-faint">No topics yet.</p>}
        <ul className="divide-y divide-white/5">
          {topics.data?.map((t) => (
            <li key={t.id} className="flex flex-wrap items-center gap-2 py-2">
              <span className="min-w-0 flex-1 text-sm text-ink">{t.name}</span>
              <select aria-label={`Status of ${t.name}`} value={t.status} className={cn("chip bg-transparent", STATUS_META[t.status].color)}
                onChange={async (e) => { await api.updateTopic(t.id, { status: e.target.value as TopicStatus }); topics.reload(true); }}>
                {Object.entries(STATUS_META).map(([k, v]) => <option key={k} value={k} className="bg-navy-900">{v.label}</option>)}
              </select>
              <Link href={`/tutor?q=${encodeURIComponent(`Teach me ${t.name}`)}`} className="text-xs text-accent hover:underline">Study</Link>
              <button aria-label="Delete topic" className="text-ink-faint hover:text-rose-300" onClick={async () => { await api.deleteTopic(t.id); topics.reload(true); }}><Trash2 className="h-3.5 w-3.5" /></button>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h3 className="section-title mb-2">Documents</h3>
        {docs.loading ? <Spinner /> : docs.data?.length === 0 ? <p className="text-sm text-ink-faint">No documents in this subject.</p> : (
          <ul className="space-y-1">{docs.data?.map((d) => (
            <li key={d.id}><Link href={`/library/${d.id}`} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-white/5">
              <FileIcon type={d.file_type} className="h-4 w-4 text-accent" /><span className="truncate">{d.title}</span>
              {d.subject_suggested && <Badge>suggested</Badge>}</Link></li>))}</ul>
        )}
      </div>
    </div>
  );
}

export default function SubjectsPage() {
  const { subjects, refreshSubjects } = useAppStatus();
  const [open, setOpen] = useState<Subject | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [color, setColor] = useState("#22d3ee");
  const [error, setError] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    try { await api.createSubject({ name, description: desc, color }); setCreating(false); setName(""); setDesc(""); refreshSubjects(); }
    catch (err) { setError((err as Error).message); }
  }

  return (
    <div>
      <PageHeader title="Subjects" icon={<BookMarked />} subtitle="Subject → topic → document → page. Organise your library and track topics."
        actions={<Button variant="outline" onClick={() => setCreating(true)}><Plus className="h-4 w-4" />Custom subject</Button>} />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {subjects.map((s) => (
          <Card key={s.id} className="card-hover cursor-pointer p-5" onClick={() => setOpen(s)}>
            <div className="flex items-start gap-3">
              <span className="mt-1 h-3 w-3 shrink-0 rounded-full" style={{ background: s.color, boxShadow: `0 0 12px ${s.color}` }} />
              <div className="min-w-0 flex-1">
                <div className="font-semibold text-white">{s.name}</div>
                <div className="mt-0.5 line-clamp-2 text-xs text-ink-muted">{s.description}</div>
              </div>
              {s.is_custom && <button aria-label="Delete subject" className="text-ink-faint hover:text-rose-300"
                onClick={async (e) => { e.stopPropagation(); if (confirm(`Delete subject ${s.name}?`)) { await api.deleteSubject(s.id); refreshSubjects(); } }}><Trash2 className="h-4 w-4" /></button>}
            </div>
            <div className="mt-4 flex gap-1.5"><Badge>{s.document_count} documents</Badge><Badge>{s.topic_count} topics</Badge>{s.is_custom && <Badge tone="violet">Custom</Badge>}</div>
          </Card>
        ))}
      </div>
      <Modal open={!!open} onClose={() => setOpen(null)} title={open?.name ?? ""}>{open && <SubjectDetail subject={open} />}</Modal>
      <Modal open={creating} onClose={() => setCreating(false)} title="New custom subject">
        <form onSubmit={create} className="space-y-3">
          <div><label className="label">Name</label><input required minLength={2} className="input" value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div><label className="label">Description</label><input className="input" value={desc} onChange={(e) => setDesc(e.target.value)} /></div>
          <div><label className="label">Colour</label><input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-9 w-16 rounded bg-transparent" /></div>
          {error && <Alert tone="danger">{error}</Alert>}
          <Button type="submit" variant="primary">Create subject</Button>
        </form>
      </Modal>
    </div>
  );
}
