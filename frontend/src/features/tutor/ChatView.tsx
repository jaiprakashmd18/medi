"use client";

import {
  BookOpen, Bot, ChevronRight, Cloud, Copy, Cpu, FlaskConical, HeartPulse, Image as ImageIcon, Lightbulb, ListTree,
  Mic, MicOff, Pause, Play, Quote, Send, Sparkles, Square, Target, Volume2,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Alert, Badge, Button, Segmented, Spinner } from "@/components/ui";
import { useAppStatus } from "@/hooks/useAppStatus";
import { useSpeechRecognition, useSpeechSynthesis } from "@/hooks/useSpeech";
import { cn, LEVELS } from "@/lib/utils";
import { api, ApiError, streamChat } from "@/services/api";
import type { ChatMessage, Source } from "@/types/api";

import { Markdown } from "./Markdown";
import { RankerBadge } from "./RankerBadge";

export const QUICK_ACTIONS = [
  { id: "simple", label: "Explain simply", icon: Lightbulb },
  { id: "in_depth", label: "In depth", icon: BookOpen },
  { id: "example", label: "Give an example", icon: Sparkles },
  { id: "mechanism", label: "Mechanism", icon: ListTree },
  { id: "diagram", label: "Explain this diagram", icon: ImageIcon, needsPage: true },
  { id: "clinical", label: "Clinical correlation", icon: HeartPulse },
  { id: "revision_notes", label: "Revision notes", icon: FlaskConical },
  { id: "test_me", label: "Test me", icon: Target },
  { id: "continue", label: "Continue", icon: ChevronRight },
] as const;

const GROUNDING: Record<string, { label: string; tone: "ok" | "warn" | "violet"; title: string }> = {
  documents: { label: "From your documents", tone: "ok", title: "The answer cites passages from your uploaded documents." },
  insufficient: { label: "Documents only partly cover this", tone: "warn",
    title: "Retrieved passages were weakly related; parts of the answer are general AI knowledge." },
  general: { label: "General AI knowledge", tone: "violet",
    title: "No passages from your documents were cited. Verify against authoritative references." },
};

interface Props {
  documentIds?: string[];
  subjectId?: number | null;
  pageNumber?: number | null;
  pageLabel?: string;
  conversationId?: string | null;
  onConversation?: (id: string) => void;
  onCite?: (s: Source) => void;
  initialPrompt?: string | null;
  compact?: boolean;
}

type UIMessage = ChatMessage & { sources?: Source[]; key?: string };

export function ChatView({ documentIds = [], subjectId, pageNumber, pageLabel, conversationId: convProp,
  onConversation, onCite, initialPrompt, compact }: Props) {
  const { settings } = useAppStatus();
  const [level, setLevel] = useState<number>(settings?.default_teaching_level ?? 2);
  const [conversationId, setConversationId] = useState<string | null>(convProp ?? null);
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [loadingConv, setLoadingConv] = useState(false);
  const [voiceMode, setVoiceMode] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const sentInitial = useRef(false);
  const selfCreated = useRef<string | null>(null);
  const tts = useSpeechSynthesis(settings?.voice_rate ?? 1, settings?.voice_name);
  const sendRef = useRef<(text: string, action?: string | null) => void>(() => {});
  const stt = useSpeechRecognition((text) => sendRef.current(text));

  useEffect(() => { if (settings) setLevel(settings.default_teaching_level); }, [settings?.default_teaching_level]); // eslint-disable-line

  // load an existing conversation
  useEffect(() => {
    if (convProp && convProp === selfCreated.current) return; // created by this view mid-stream
    setConversationId(convProp ?? null);
    if (!convProp) { setMessages([]); return; }
    let cancel = false;
    setLoadingConv(true);
    api.conversation(convProp).then((c) => {
      if (cancel) return;
      setMessages(c.messages.map((m) => ({ ...m, sources: m.citations })));
      setLevel(c.teaching_level);
    }).catch((e) => !cancel && setError(e)).finally(() => !cancel && setLoadingConv(false));
    return () => { cancel = true; };
  }, [convProp]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages]);

  const send = useCallback(async (text: string, action: string | null = null) => {
    if (busy || (!text.trim() && !action)) return;
    tts.stop();
    setError(null);
    setBusy(true);
    const now = new Date().toISOString();
    const qa = QUICK_ACTIONS.find((a) => a.id === action);
    const userMsg: UIMessage = { id: `u-${now}`, role: "user", content: text.trim() || qa?.label || "", action,
      teaching_level: level, provider: null, model: null, grounding: null, status: "complete", meta: {}, created_at: now, citations: [] };
    const aiId = `a-${now}`;
    const aiMsg: UIMessage = { id: aiId, key: aiId, role: "assistant", content: "", action, teaching_level: level, provider: null,
      model: null, grounding: null, status: "streaming", meta: {}, created_at: now, citations: [], sources: [] };
    setMessages((m) => [...m, userMsg, aiMsg]);
    setInput("");
    const patch = (fn: (m: UIMessage) => UIMessage) => setMessages((all) => all.map((m) => (m.key === aiId ? fn(m) : m)));
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    let finalText = "";
    try {
      await streamChat({ message: text, conversation_id: conversationId, teaching_level: level, action,
        document_ids: documentIds, subject_id: subjectId ?? null, page_number: pageNumber ?? null }, {
        onMeta: (m) => {
          if (!conversationId) {
            selfCreated.current = m.conversation_id;
            setConversationId(m.conversation_id);
            onConversation?.(m.conversation_id);
          }
          patch((x) => ({ ...x, provider: m.provider, model: m.model, sources: m.sources,
            meta: { ...x.meta, routing: m.routing, retrieval_note: m.retrieval_note, ranker: m.ranker,
              rerank_note: m.rerank_note } }));
        },
        onDelta: (t) => { finalText += t; patch((x) => ({ ...x, content: x.content + t })); },
        onDone: (d) => {
          patch((x) => ({ ...x, id: d.message_id, status: d.truncated ? "partial" : "complete", grounding: d.grounding as UIMessage["grounding"],
            provider: d.provider, model: d.model, meta: { ...x.meta, invalid_citations: d.invalid_citations },
            sources: (x.sources ?? []).map((s) => ({ ...s, used_in_answer: d.used_citations.includes(s.label) })) }));
          if (voiceMode && finalText) tts.speak(d.message_id, finalText);
        },
        onError: (e) => {
          patch((x) => ({ ...x, status: "error", meta: { ...x.meta, error: e.message } }));
          setError(new ApiError(502, e.code, e.message));
        },
      }, ctrl.signal);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(0, "error", (e as Error).message);
      setError(err);
      setMessages((all) => all.filter((m) => m.key !== aiId));
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }, [busy, conversationId, level, documentIds, subjectId, pageNumber, onConversation, tts, voiceMode]);
  sendRef.current = send;

  useEffect(() => {
    if (initialPrompt && !sentInitial.current && !convProp) {
      sentInitial.current = true;
      send(initialPrompt);
    }
  }, [initialPrompt, convProp, send]);

  const lastUser = [...messages].reverse().find((m) => m.role === "user");

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* level selector */}
      <div className={cn("flex flex-wrap items-center gap-2 border-b border-white/5", compact ? "px-3 py-2" : "px-4 py-3")}>
        <span className="text-[11px] font-medium uppercase tracking-wider text-ink-faint">Level</span>
        <Segmented size="sm" value={level} onChange={setLevel}
          options={LEVELS.map((l) => ({ value: l.level, label: compact ? `${l.level}` : `${l.level} · ${l.name}`, title: `Level ${l.level}: ${l.long}` }))} />
        {compact && <span className="text-[11px] text-ink-muted">{LEVELS[level - 1]?.long}</span>}
        <div className="ml-auto flex items-center gap-1">
          {tts.supported && (
            <Button size="sm" variant={voiceMode ? "outline" : "ghost"} onClick={() => { setVoiceMode(!voiceMode); tts.stop(); }}
              title="Voice mode: answers are read aloud automatically" aria-pressed={voiceMode}>
              <Volume2 className="h-3.5 w-3.5" />{!compact && "Voice"}
            </Button>
          )}
        </div>
      </div>

      {/* messages */}
      <div className={cn("min-h-0 flex-1 space-y-4 overflow-y-auto", compact ? "p-3" : "p-4 lg:p-6")} aria-live="polite">
        {loadingConv && <div className="flex justify-center py-8"><Spinner /></div>}
        {!loadingConv && messages.length === 0 && (
          <div className="mx-auto max-w-md py-8 text-center">
            <div className="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-2xl border border-accent/20 bg-accent/10 text-accent"><Bot /></div>
            <h3 className="font-semibold text-white">Your medical professor is ready</h3>
            <p className="mt-1 text-sm text-ink-muted">
              {pageLabel ? <>Ask anything about <span className="text-ink">{pageLabel}</span>, or use a quick action below.</>
                : documentIds.length ? "Ask about the selected documents." : "Ask about anything in your library."}
            </p>
          </div>
        )}
        {messages.map((m) => m.role === "user" ? (
          <div key={m.id} className="flex justify-end">
            <div className="max-w-[85%] rounded-2xl rounded-br-md bg-gradient-to-br from-cyan-500/25 to-teal-500/15 px-4 py-2.5 text-sm text-white">
              {m.action && <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-accent-soft">{QUICK_ACTIONS.find((a) => a.id === m.action)?.label}</div>}
              {m.content}
            </div>
          </div>
        ) : (
          <AssistantMessage key={m.key ?? m.id} m={m} onCite={onCite} tts={tts}
            onRetry={m.status === "error" && lastUser ? () => send(lastUser.content, lastUser.action) : undefined} />
        ))}
        <div ref={endRef} />
      </div>

      {/* composer */}
      <div className={cn("border-t border-white/5 bg-navy-900/60", compact ? "p-2.5" : "p-3 lg:p-4")}>
        {error && <Alert tone="danger" className="mb-2" onClose={() => setError(null)} title={error.code === "no_provider" || error.code === "consent_required" ? "AI unavailable" : undefined}>
          {error.message}
        </Alert>}
        <div className="mb-2 flex gap-1.5 overflow-x-auto pb-1">
          {QUICK_ACTIONS.filter((a) => !("needsPage" in a) || pageNumber).map(({ id, label, icon: Icon }) => (
            <button key={id} disabled={busy || (id !== "diagram" && messages.length === 0 && !pageNumber)}
              onClick={() => send("", id)}
              className="focus-ring inline-flex shrink-0 items-center gap-1.5 rounded-full border border-white/10 bg-navy-850 px-2.5 py-1 text-[11px] font-medium text-ink-muted transition hover:border-accent/40 hover:text-accent-soft disabled:opacity-40">
              <Icon className="h-3 w-3" />{label}
            </button>
          ))}
        </div>
        <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); send(input); }}>
          <textarea value={stt.listening ? input + stt.interim : input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
            rows={compact ? 1 : 2} placeholder={pageLabel ? `Ask about ${pageLabel}…` : "Ask your medical tutor…"}
            aria-label="Message" className="input max-h-40 min-h-[42px] flex-1 resize-none" />
          {stt.supported && (
            <Button type="button" size="icon" variant={stt.listening ? "danger" : "ghost"} title={stt.listening ? "Stop listening" : "Speak your question"}
              onClick={() => { tts.stop(); if (stt.listening) stt.stop(); else stt.start(); }}>
              {stt.listening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
            </Button>
          )}
          {busy ? (
            <Button type="button" size="icon" variant="secondary" title="Stop" onClick={() => abortRef.current?.abort()}><Square className="h-4 w-4" /></Button>
          ) : (
            <Button type="submit" size="icon" variant="primary" title="Send" disabled={!input.trim()}><Send className="h-4 w-4" /></Button>
          )}
        </form>
        {stt.error && <p className="mt-1 text-[11px] text-rose-300">{stt.error}</p>}
      </div>
    </div>
  );
}

function AssistantMessage({ m, onCite, tts, onRetry }: { m: UIMessage; onCite?: (s: Source) => void;
  tts: ReturnType<typeof useSpeechSynthesis>; onRetry?: () => void }) {
  const [showAll, setShowAll] = useState(false);
  const sources = m.sources ?? m.citations ?? [];
  const used = sources.filter((s) => s.used_in_answer);
  const others = sources.filter((s) => !s.used_in_answer);
  const g = m.grounding ? GROUNDING[m.grounding] : null;
  const invalid = m.meta?.invalid_citations ?? [];
  const speaking = tts.speakingId === m.id;
  return (
    <div className="animate-fade-in rounded-2xl rounded-tl-md border border-white/[0.06] bg-navy-850/70 p-4">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        {m.provider && (
          <Badge tone={m.provider === "anthropic" ? "accent" : "info"} title={m.meta?.routing}>
            {m.provider === "anthropic" ? <Cloud className="h-3 w-3" /> : <Cpu className="h-3 w-3" />}
            {m.provider === "anthropic" ? "Claude" : "Local"} · {m.model}
          </Badge>
        )}
        {m.teaching_level && <Badge>L{m.teaching_level} · {LEVELS[m.teaching_level - 1]?.name}</Badge>}
        {g && <Badge tone={g.tone} title={g.title}>{g.label}</Badge>}
        {m.status !== "streaming" && <RankerBadge ranker={m.meta?.ranker} note={m.meta?.rerank_note} />}
        {m.status === "partial" && <Badge tone="warn">Answer truncated — ask “Continue”</Badge>}
        <div className="ml-auto flex items-center gap-0.5">
          {tts.supported && m.content && m.status !== "streaming" && (speaking ? (
            <>
              <button className="rounded p-1 text-accent hover:bg-white/5" title={tts.paused ? "Resume" : "Pause"}
                onClick={() => (tts.paused ? tts.resume() : tts.pause())}>{tts.paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}</button>
              <button className="rounded p-1 text-accent hover:bg-white/5" title="Stop" onClick={tts.stop}><Square className="h-3.5 w-3.5" /></button>
            </>
          ) : (
            <button className="rounded p-1 text-ink-faint hover:bg-white/5 hover:text-ink" title="Read aloud" onClick={() => tts.speak(m.id, m.content)}>
              <Volume2 className="h-3.5 w-3.5" /></button>
          ))}
          {m.content && <button className="rounded p-1 text-ink-faint hover:bg-white/5 hover:text-ink" title="Copy"
            onClick={() => navigator.clipboard?.writeText(m.content)}><Copy className="h-3.5 w-3.5" /></button>}
        </div>
      </div>

      {m.status === "streaming" && !m.content && (
        <div className="flex items-center gap-2 py-1 text-sm text-ink-muted">
          <span className="flex gap-1">{[0, 1, 2].map((i) => <span key={i} className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-accent" style={{ animationDelay: `${i * 0.15}s` }} />)}</span>
          {sources.length ? `Reading ${sources.length} passages from your documents…` : "Thinking…"}
        </div>
      )}
      {m.content && <Markdown content={m.content} sources={sources} onCite={onCite} />}
      {m.status === "error" && (
        <div className="mt-2 flex items-center gap-2">
          <Alert tone="danger" className="flex-1">{m.meta?.error || "The answer could not be generated."}</Alert>
          {onRetry && <Button size="sm" onClick={onRetry}>Retry</Button>}
        </div>
      )}
      {invalid.length > 0 && (
        <p className="mt-2 text-[11px] text-rose-300/90">The AI referenced source number(s) {invalid.map((n) => `[${n}]`).join(", ")} that do not exist; they are not citations and were ignored.</p>
      )}

      {sources.length > 0 && m.status !== "streaming" && (
        <div className="mt-3 border-t border-white/5 pt-3">
          <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
            <Quote className="h-3 w-3" /> Sources {used.length ? `cited (${used.length})` : "retrieved (none cited)"}
          </div>
          <ul className="space-y-1.5">
            {(used.length ? used : others.slice(0, 3)).map((s) => <SourceItem key={s.label} s={s} onCite={onCite} />)}
          </ul>
          {used.length > 0 && others.length > 0 && (
            <>
              <button className="mt-1.5 text-[11px] text-ink-faint hover:text-accent" onClick={() => setShowAll(!showAll)}>
                {showAll ? "Hide" : "Show"} {others.length} other retrieved passage(s)
              </button>
              {showAll && <ul className="mt-1.5 space-y-1.5 opacity-75">{others.map((s) => <SourceItem key={s.label} s={s} onCite={onCite} />)}</ul>}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function SourceItem({ s, onCite }: { s: Source; onCite?: (s: Source) => void }) {
  return (
    <li>
      <button onClick={() => onCite?.(s)} className="group flex w-full items-start gap-2 rounded-lg px-1.5 py-1 text-left hover:bg-white/[0.03]">
        <span className="mt-0.5 grid h-4 min-w-4 place-items-center rounded border border-accent/40 bg-accent/10 px-0.5 text-[10px] font-semibold text-accent-soft">{s.label}</span>
        <span className="min-w-0 text-xs">
          <span className="font-medium text-ink group-hover:text-accent-soft">{s.document_title}</span>
          <span className="text-ink-muted"> · {s.page_kind} {s.page_number}{s.section ? ` · ${s.section}` : ""}</span>
          <span className="mt-0.5 line-clamp-2 block text-ink-faint">{s.snippet}</span>
        </span>
      </button>
    </li>
  );
}
