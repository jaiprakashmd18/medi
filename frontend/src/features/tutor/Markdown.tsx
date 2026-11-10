"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";
import type { Source } from "@/types/api";

const CITE = /\[(\d{1,2}(?:\s*[,–-]\s*\d{1,2})*)\](?!\()/g;

/** Expand "[1, 3]" / "[2-4]" into individual citation links the renderer turns into chips. */
export function linkCitations(md: string): string {
  return md.replace(CITE, (_m, inner: string) => {
    const nums: number[] = [];
    for (const part of inner.split(/\s*,\s*/)) {
      const range = part.split(/\s*[–-]\s*/).map(Number);
      if (range.length === 2 && range[1] - range[0] < 10) for (let i = range[0]; i <= range[1]; i++) nums.push(i);
      else nums.push(Number(part));
    }
    return nums.map((n) => `[${n}](#cite-${n})`).join("");
  });
}

export function CitationChip({ n, source, onClick }: { n: number; source?: Source; onClick?: (s: Source) => void }) {
  if (!source)
    return (
      <span title="This reference number does not match any retrieved source and was ignored."
        className="mx-0.5 inline-flex h-[18px] items-center rounded border border-rose-400/40 bg-rose-400/10 px-1 align-text-top text-[10px] font-semibold text-rose-300">
        ?{n}
      </span>
    );
  return (
    <button type="button" onClick={() => onClick?.(source)}
      title={`${source.document_title} — ${source.page_kind} ${source.page_number}${source.section ? ` · ${source.section}` : ""}`}
      className="mx-0.5 inline-flex h-[18px] items-center rounded border border-accent/40 bg-accent/10 px-1 align-text-top text-[10px] font-semibold text-accent-soft transition hover:bg-accent/25">
      {n}
    </button>
  );
}

export function Markdown({ content, sources = [], onCite, className }: { content: string; sources?: Source[];
  onCite?: (s: Source) => void; className?: string }) {
  const byLabel = new Map(sources.map((s) => [s.label, s]));
  return (
    <div className={cn("prose-med", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}
        components={{
          a({ href, children }) {
            const m = href?.match(/^#cite-(\d+)$/);
            if (m) return <CitationChip n={Number(m[1])} source={byLabel.get(Number(m[1]))} onClick={onCite} />;
            return <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>;
          },
          h3({ children }) {
            const text = String(children);
            const ai = /additional explanation \(ai-generated\)/i.test(text);
            return <h3 className={ai ? "!text-violet-300" : undefined}>{ai && "✦ "}{children}</h3>;
          },
        }}>
        {linkCitations(content)}
      </ReactMarkdown>
    </div>
  );
}
