"use client";

import { Library, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Alert, Button, EmptyState, PageHeader, Segmented, Spinner } from "@/components/ui";
import { DocumentCard } from "@/features/library/DocumentCard";
import { UploadDropzone } from "@/features/library/Upload";
import { useAppStatus } from "@/hooks/useAppStatus";
import { useAsync, usePolling } from "@/hooks/useAsync";
import { isProcessing } from "@/lib/utils";
import { api } from "@/services/api";
import type { SearchResult } from "@/types/api";

export default function LibraryPage() {
  const { subjects } = useAppStatus();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [subjectId, setSubjectId] = useState<number | null>(null);
  const [type, setType] = useState("");
  const [sort, setSort] = useState("recent");
  const [semantic, setSemantic] = useState<{ results: SearchResult[]; note: string } | null>(null);
  const [searching, setSearching] = useState(false);
  const docs = useAsync(() => api.documents({ q: query, subject_id: subjectId, file_type: type, sort }), [query, subjectId, type, sort]);
  const anyProcessing = !!docs.data?.some((d) => isProcessing(d.status));
  usePolling(() => docs.reload(true), 1500, anyProcessing);

  useEffect(() => { const t = setTimeout(() => setQuery(q), 300); return () => clearTimeout(t); }, [q]);

  async function semanticSearch() {
    if (q.trim().length < 2) return;
    setSearching(true);
    try { setSemantic(await api.search(q, [], subjectId)); } finally { setSearching(false); }
  }

  return (
    <div>
      <PageHeader title="My Library" subtitle="Your private medical study materials, analysed and searchable." icon={<Library />} />
      <UploadDropzone onUploaded={() => docs.reload(true)} />

      <div className="mt-8 flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
          <input className="input pl-9" placeholder="Search titles and document text…" value={q} onChange={(e) => { setQ(e.target.value); setSemantic(null); }}
            onKeyDown={(e) => e.key === "Enter" && semanticSearch()} aria-label="Search documents" />
        </div>
        <Button onClick={semanticSearch} loading={searching} disabled={q.trim().length < 2} title="Search meaning across all passages">Semantic search</Button>
        <select className="input lg:w-44" value={subjectId ?? ""} onChange={(e) => setSubjectId(e.target.value ? Number(e.target.value) : null)} aria-label="Filter by subject">
          <option value="">All subjects</option>
          {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <Segmented value={type} onChange={setType} options={[{ value: "", label: "All" }, { value: "pdf", label: "PDF" },
          { value: "pptx", label: "PPTX" }, { value: "docx", label: "DOCX" }, { value: "image", label: "Images" }]} />
        <select className="input lg:w-36" value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort">
          <option value="recent">Newest</option><option value="title">Title</option><option value="opened">Last opened</option>
        </select>
      </div>

      {semantic && (
        <div className="card mt-4 p-4">
          <div className="mb-2 flex items-center justify-between"><h2 className="section-title">Passages matching “{q}”</h2>
            <button className="text-xs text-ink-faint hover:text-ink" onClick={() => setSemantic(null)}>Close</button></div>
          {semantic.results.length === 0 ? <p className="text-sm text-ink-muted">{semantic.note || "No matches."}</p> : (
            <ul className="divide-y divide-white/5">
              {semantic.results.map((r) => (
                <li key={r.chunk_id} className="py-2.5">
                  <Link href={`/library/${r.document_id}?page=${r.page_number}`} className="text-sm font-medium text-accent-soft hover:underline">
                    {r.document_title} · {r.page_kind} {r.page_number}</Link>
                  {r.section && <span className="ml-2 text-xs text-ink-faint">{r.section}</span>}
                  <p className="mt-0.5 line-clamp-2 text-xs text-ink-muted">{r.text}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="mt-6">
        {docs.error && <Alert tone="danger">{docs.error.message}</Alert>}
        {docs.loading && !docs.data ? <div className="flex justify-center py-12"><Spinner /></div>
          : docs.data && docs.data.length === 0 ? (
            <EmptyState icon={<Library />} title={query || subjectId || type ? "No documents match" : "Your library is empty"}>
              Upload lecture slides, textbook chapters or notes. MEDI-GENIUS extracts the text, tables and diagrams and teaches from them.
            </EmptyState>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {docs.data?.map((d) => <DocumentCard key={d.id} doc={d} subjects={subjects} onChanged={() => docs.reload(true)} />)}
            </div>
          )}
      </div>
    </div>
  );
}
