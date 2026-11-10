/**
 * Typed client for the MEDI-GENIUS backend.
 * No secrets live in the frontend: AI keys stay in the backend .env.
 */
import type {
  AIMode, Attempt, ConversationDetail, Conversation, Dashboard, DocImage, DocumentDetail, DocumentSummary,
  Flashcard, Health, LabelBox, PageDetail, PageSummary, Progress, ProvidersResponse, QuizDetail, QuizSummary,
  QuestionType, RevisionStats, SearchResult, Source, Subject, Topic, TopicStatus, UserSettings,
} from "@/types/api";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
const TOKEN_KEY = "medigenius.token";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message);
  }
}

export function getToken(): string | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable */
  }
}

/** Absolute URL for backend-relative resources (images, files). Adds the token for <img> tags. */
export function assetUrl(path: string): string {
  const url = path.startsWith("http") ? path : `${API_URL}${path}`;
  const t = getToken();
  return t ? `${url}${url.includes("?") ? "&" : "?"}access_token=${encodeURIComponent(t)}` : url;
}

function headers(extra?: HeadersInit): HeadersInit {
  const h: Record<string, string> = {};
  const t = getToken();
  if (t) h.Authorization = `Bearer ${t}`;
  return { ...h, ...(extra as Record<string, string>) };
}

async function parseError(res: Response): Promise<ApiError> {
  let code = "http_error";
  let message = `Request failed (${res.status})`;
  let details: unknown;
  try {
    const body = await res.json();
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      details = body.error.details;
    }
  } catch {
    /* non-JSON */
  }
  return new ApiError(res.status, code, message, details);
}

export async function request<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...rest } = init;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...rest,
      headers: headers(json !== undefined ? { "Content-Type": "application/json", ...(rest.headers || {}) } : rest.headers),
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
  } catch {
    throw new ApiError(0, "network_error", `Cannot reach the MEDI-GENIUS backend at ${API_URL}. Is it running?`);
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function qs(params: Record<string, string | number | undefined | null | string[]>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => u.append(k, x));
    else u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

/** Upload with progress events (fetch has no upload progress, so XHR is used). */
export function uploadDocuments(
  files: File[], subjectId: number | null, onProgress: (pct: number) => void,
): Promise<{ documents: DocumentSummary[]; errors: { filename: string; message: string }[] }> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    if (subjectId) form.append("subject_id", String(subjectId));
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/api/documents/upload`);
    const t = getToken();
    if (t) xhr.setRequestHeader("Authorization", `Bearer ${t}`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((100 * e.loaded) / e.total));
    xhr.onerror = () => reject(new ApiError(0, "network_error", "Upload failed: backend unreachable."));
    xhr.onload = () => {
      let body: any = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* ignore */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new ApiError(xhr.status, body?.error?.code ?? "upload_failed", body?.error?.message ?? "Upload failed",
        body?.error?.details));
    };
    xhr.send(form);
  });
}

export interface StreamHandlers {
  onMeta?: (m: { conversation_id: string; provider: string; provider_kind: string; model: string; routing: string;
    sources: Source[]; retrieval_sufficient: boolean; retrieval_note: string; teaching_level: number }) => void;
  onDelta?: (text: string) => void;
  onDone?: (d: { message_id: string; grounding: string; used_citations: number[]; invalid_citations: number[];
    provider: string; model: string; truncated: boolean }) => void;
  onError?: (e: { code: string; message: string; message_id?: string }) => void;
}

export interface ChatRequest {
  message: string;
  conversation_id?: string | null;
  teaching_level?: number;
  action?: string | null;
  document_ids?: string[];
  subject_id?: number | null;
  page_number?: number | null;
}

/** Streams a tutor answer over Server-Sent Events (POST). */
export async function streamChat(body: ChatRequest, h: StreamHandlers, signal?: AbortSignal): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/tutor/chat/stream`, {
      method: "POST", headers: headers({ "Content-Type": "application/json" }), body: JSON.stringify(body), signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    throw new ApiError(0, "network_error", `Cannot reach the MEDI-GENIUS backend at ${API_URL}.`);
  }
  if (!res.ok || !res.body) throw await parseError(res);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const raw = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const ev = parseSSE(raw);
      if (!ev) continue;
      if (ev.event === "meta") h.onMeta?.(ev.data);
      else if (ev.event === "delta") h.onDelta?.(ev.data.text);
      else if (ev.event === "done") h.onDone?.(ev.data);
      else if (ev.event === "error") h.onError?.(ev.data);
    }
  }
}

export function parseSSE(raw: string): { event: string; data: any } | null {
  let event = "message";
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (!data.length) return null;
  try {
    return { event, data: JSON.parse(data.join("\n")) };
  } catch {
    return null;
  }
}

export const api = {
  health: () => request<Health>("/api/health"),
  providers: (refresh = false) => request<ProvidersResponse>(`/api/ai/providers${refresh ? "?refresh=true" : ""}`),
  authConfig: () => request<{ auth_mode: string }>("/api/auth/config"),
  login: (email: string, password: string) =>
    request<{ token: string }>("/api/auth/login", { method: "POST", json: { email, password } }),
  register: (email: string, password: string, display_name: string) =>
    request<{ token: string }>("/api/auth/register", { method: "POST", json: { email, password, display_name } }),
  me: () => request<{ id: string; email: string; display_name: string }>("/api/auth/me"),

  dashboard: () => request<Dashboard>("/api/dashboard"),
  documents: (p: { q?: string; subject_id?: number | null; status?: string; file_type?: string; sort?: string } = {}) =>
    request<DocumentSummary[]>(`/api/documents${qs(p)}`),
  document: (id: string) => request<DocumentDetail>(`/api/documents/${id}`),
  documentStatus: (id: string) => request<Pick<DocumentSummary, "id" | "status" | "progress" | "stage_message" |
    "error_message" | "warnings" | "page_count">>(`/api/documents/${id}/status`),
  updateDocument: (id: string, body: { title?: string; subject_id?: number; clear_subject?: boolean }) =>
    request<DocumentSummary>(`/api/documents/${id}`, { method: "PATCH", json: body }),
  deleteDocument: (id: string) => request<void>(`/api/documents/${id}`, { method: "DELETE" }),
  reprocess: (id: string) => request<DocumentSummary>(`/api/documents/${id}/reprocess`, { method: "POST" }),
  markViewed: (id: string, page_number: number) =>
    request<{ ok: boolean }>(`/api/documents/${id}/viewed`, { method: "POST", json: { page_number } }),
  pages: (id: string) => request<PageSummary[]>(`/api/documents/${id}/pages`),
  page: (id: string, n: number) => request<PageDetail>(`/api/documents/${id}/pages/${n}`),
  pageImageUrl: (id: string, n: number, scale: number) => assetUrl(`/api/documents/${id}/pages/${n}/image?scale=${scale}`),
  fileUrl: (id: string) => assetUrl(`/api/documents/${id}/file`),
  documentImages: (id: string) => request<DocImage[]>(`/api/documents/${id}/images`),
  allImages: (p: { document_id?: string; subject_id?: number | null } = {}) => request<DocImage[]>(`/api/images${qs(p)}`),
  imageLabels: (imageId: number) =>
    request<{ width: number; height: number; labels: LabelBox[]; ocr_available: boolean; note: string }>(
      `/api/images/${imageId}/labels`),
  search: (q: string, document_ids: string[] = [], subject_id?: number | null) =>
    request<{ results: SearchResult[]; note: string; sufficient: boolean }>(`/api/search${qs({ q, document_ids, subject_id })}`),

  subjects: () => request<Subject[]>("/api/subjects"),
  createSubject: (body: { name: string; description?: string; color?: string }) =>
    request<Subject>("/api/subjects", { method: "POST", json: body }),
  deleteSubject: (id: number) => request<void>(`/api/subjects/${id}`, { method: "DELETE" }),
  topics: (subject_id?: number | null) => request<Topic[]>(`/api/topics${qs({ subject_id })}`),
  createTopic: (body: { name: string; subject_id?: number | null }) =>
    request<Topic>("/api/topics", { method: "POST", json: body }),
  updateTopic: (id: number, body: { status?: TopicStatus; name?: string }) =>
    request<Topic>(`/api/topics/${id}`, { method: "PATCH", json: body }),
  deleteTopic: (id: number) => request<void>(`/api/topics/${id}`, { method: "DELETE" }),

  conversations: (document_id?: string) => request<Conversation[]>(`/api/tutor/history${qs({ document_id })}`),
  conversation: (id: string) => request<ConversationDetail>(`/api/tutor/conversations/${id}`),
  deleteConversation: (id: string) => request<void>(`/api/tutor/conversations/${id}`, { method: "DELETE" }),
  explainDiagram: (image_id: number, teaching_level?: number, question?: string) =>
    request<{ explanation: string; provider: string; model: string; vision_used: boolean; sources: Source[];
      used_citations: number[]; notice: string | null; routing: string }>(
      "/api/tutor/diagram", { method: "POST", json: { image_id, teaching_level, question } }),

  quizzes: () => request<QuizSummary[]>("/api/quizzes"),
  quiz: (id: string) => request<QuizDetail>(`/api/quizzes/${id}`),
  generateQuiz: (body: { document_ids: string[]; subject_id?: number | null; topic?: string | null;
    difficulty: string; num_questions: number; question_types: QuestionType[]; title?: string }) =>
    request<QuizDetail>("/api/quizzes/generate", { method: "POST", json: body }),
  submitQuiz: (id: string, answers: Record<string, unknown>, duration_seconds?: number) =>
    request<Attempt>(`/api/quizzes/${id}/submit`, { method: "POST", json: { answers, duration_seconds } }),
  quizResults: (id: string) => request<{ quiz: QuizSummary; questions: { index: number; type: QuestionType;
    prompt: string; options: string[] }[]; attempts: Attempt[] }>(`/api/quizzes/${id}/results`),
  deleteQuiz: (id: string) => request<void>(`/api/quizzes/${id}`, { method: "DELETE" }),

  revision: () => request<{ stats: RevisionStats; due: Flashcard[]; weak_topics: Topic[] }>("/api/revision"),
  cards: () => request<Flashcard[]>("/api/revision/cards"),
  generateCards: (body: { document_ids: string[]; subject_id?: number | null; topic?: string | null; count: number }) =>
    request<{ cards: Flashcard[]; warnings: string[]; provider: string; model: string }>(
      "/api/revision/generate", { method: "POST", json: body }),
  createCard: (body: { front: string; back: string; topic?: string | null }) =>
    request<Flashcard>("/api/revision/cards", { method: "POST", json: body }),
  deleteCard: (id: number) => request<void>(`/api/revision/cards/${id}`, { method: "DELETE" }),
  reviewCard: (id: number, rating: number) =>
    request<Flashcard>(`/api/revision/cards/${id}/review`, { method: "POST", json: { rating } }),

  progress: () => request<Progress>("/api/progress"),
  settings: () => request<UserSettings>("/api/settings"),
  updateSettings: (body: Partial<UserSettings> & { ai_mode?: AIMode }) =>
    request<UserSettings>("/api/settings", { method: "PUT", json: body }),
  exportUrl: () => assetUrl("/api/export"),
  deleteAllData: () => request<{ ok: boolean }>("/api/account/data?confirm=DELETE", { method: "DELETE" }),
};
