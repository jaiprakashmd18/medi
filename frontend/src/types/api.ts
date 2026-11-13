export type DocStatus =
  | "uploaded" | "validating" | "stored" | "extracting" | "ocr" | "analysing_images" | "chunking"
  | "embedding" | "indexing" | "ready" | "partial" | "failed";

export interface DocumentSummary {
  id: string;
  title: string;
  original_filename: string;
  file_type: "pdf" | "pptx" | "docx" | "image";
  mime_type: string;
  size_bytes: number;
  status: DocStatus;
  progress: number;
  stage_message: string;
  error_message: string | null;
  warnings: string[];
  page_count: number;
  chunk_count: number;
  image_count: number;
  subject_id: number | null;
  subject_suggested: boolean;
  topic_id: number | null;
  has_preview: boolean;
  created_at: string;
  updated_at: string;
  processed_at: string | null;
  last_opened_at: string | null;
  last_page_viewed: number;
}

export interface OutlineItem { level: number; title: string; page: number }

export interface DocumentDetail extends DocumentSummary {
  outline: OutlineItem[];
  page_kind: "page" | "slide" | "section" | "image";
}

export interface PageSummary {
  page_number: number;
  kind: string;
  title: string | null;
  status: "ok" | "partial" | "failed";
  is_scanned: boolean;
  ocr_used: boolean;
  image_count: number;
  table_count: number;
  char_count: number;
  has_notes: boolean;
}

export interface DocImage {
  id: number;
  page_number: number;
  index_on_page: number;
  width: number;
  height: number;
  ocr_text: string;
  ai_description: string | null;
  ai_provider: string | null;
  ai_model: string | null;
  origin: string;
  url: string;
  document_id?: string;
  document_title?: string;
  page_kind?: string;
}

export interface PageDetail {
  page_number: number;
  kind: string;
  title: string | null;
  text: string;
  notes: string;
  tables: { index: number; markdown: string }[];
  headings: string[];
  is_scanned: boolean;
  ocr_used: boolean;
  ocr_confidence: number | null;
  status: string;
  error: string | null;
  warnings: string[];
  width: number | null;
  height: number | null;
  images: DocImage[];
  renderable: boolean;
}

export interface Subject {
  id: number;
  name: string;
  slug: string;
  description: string;
  color: string;
  is_custom: boolean;
  document_count: number;
  topic_count: number;
}

export type TopicStatus = "not_studied" | "learning" | "needs_revision" | "understood" | "mastered";

export interface Topic {
  id: number;
  name: string;
  subject_id: number | null;
  parent_id: number | null;
  status: TopicStatus;
  status_manual: boolean;
  questions_answered: number;
  questions_correct: number;
  last_studied_at: string | null;
}

export interface Source {
  label: number;
  document_id: string | null;
  document_title: string;
  page_number: number;
  page_kind: string;
  section: string | null;
  kind?: string;
  snippet: string;
  score: number;
  chunk_id?: string | null;
  used_in_answer?: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  action: string | null;
  teaching_level: number | null;
  provider: string | null;
  model: string | null;
  grounding: "documents" | "general" | "insufficient" | null;
  status: "complete" | "error" | "partial" | "streaming";
  meta: { invalid_citations?: number[]; routing?: string; retrieval_note?: string; error?: string | null };
  created_at: string;
  citations: Source[];
}

export interface Conversation {
  id: string;
  title: string;
  document_id: string | null;
  subject_id: number | null;
  teaching_level: number;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationDetail extends Conversation { messages: ChatMessage[] }

export interface ProviderInfo {
  name: string;
  label: string;
  kind: "cloud" | "local";
  configured: boolean;
  available: boolean;
  detail: string;
  models: Record<string, string>;
  installed_models: string[];
}

export interface ProvidersResponse {
  mode: AIMode;
  cloud_consent: boolean;
  providers: ProviderInfo[];
  routes: Record<string, { ok: boolean; provider?: string; model?: string; reason: string; code?: string }>;
  billing_note: string;
  reranker?: { name: string; model: string; enabled: boolean; configured: boolean; cooldown_seconds: number;
    cooldown_reason: string | null; active_for_you: boolean; reason: string; nvidia_consent: boolean };
}

export type AIMode = "auto" | "local_only" | "cloud_only";

export interface UserSettings {
  ai_mode: AIMode;
  default_teaching_level: number;
  cloud_consent: boolean;
  cloud_consent_at: string | null;
  nvidia_consent: boolean;
  nvidia_consent_at: string | null;
  voice_rate: number;
  voice_name: string | null;
  daily_review_goal: number;
  display_name: string | null;
}

export type QuestionType = "sba" | "multi" | "true_false" | "fill_blank" | "short" | "long" | "viva" | "diagram";

export interface QuizSummary {
  id: string;
  title: string;
  subject_id: number | null;
  topic: string | null;
  difficulty: "easy" | "medium" | "hard";
  question_types: QuestionType[];
  document_ids: string[];
  provider: string | null;
  model: string | null;
  warnings: string[];
  created_at: string;
  question_count: number;
  best_percent: number | null;
  attempt_count: number;
}

export interface QuestionPublic {
  index: number;
  type: QuestionType;
  prompt: string;
  options: string[];
  topic: string | null;
  difficulty: string;
  image_id: number | null;
  image_url: string | null;
}

export interface QuizDetail extends QuizSummary { questions: QuestionPublic[] }

export interface QuestionResult {
  question_index: number;
  type: QuestionType;
  topic: string | null;
  answer: unknown;
  correct_answer: unknown;
  model_answer: string;
  key_points: string[];
  explanation: string;
  citations: Source[];
  score: number;
  correct: boolean;
  grading: "auto" | "ai" | "keyword_estimate" | "unanswered";
  feedback?: string;
  missing_points?: string[];
  grader?: string;
}

export interface Attempt {
  id: string;
  quiz_id: string;
  submitted_at: string;
  score: number;
  max_score: number;
  percent: number;
  results: QuestionResult[];
  topic_breakdown: { topic: string; questions: number; score: number; percent: number; weak: boolean }[];
  duration_seconds: number | null;
  weak_topics: string[];
  recommendations: string[];
}

export interface Flashcard {
  id: number;
  front: string;
  back: string;
  topic: string | null;
  subject_id: number | null;
  document_id: string | null;
  citation: Source | null;
  origin: "ai" | "manual" | "quiz_mistake";
  provider: string | null;
  ease: number;
  interval_days: number;
  repetitions: number;
  lapses: number;
  due_at: string;
  last_reviewed_at: string | null;
  suspended: boolean;
  created_at: string;
}

export interface RevisionStats {
  total: number;
  due_now: number;
  due_within_24h: number;
  reviewed_today: number;
  mature: number;
}

export interface StudySessionInfo {
  id: string;
  kind: "reading" | "tutor" | "quiz" | "revision" | "visual";
  title: string;
  document_id: string | null;
  conversation_id: string | null;
  quiz_id: string | null;
  started_at: string;
  last_activity_at: string;
  activity_count: number;
}

export interface Dashboard {
  user: { display_name: string };
  recent_documents: DocumentSummary[];
  continue_learning: DocumentSummary[];
  recent_conversations: { id: string; title: string; updated_at: string; document_id: string | null }[];
  recent_sessions: StudySessionInfo[];
  revision: RevisionStats;
  topic_status: Partial<Record<TopicStatus, number>>;
  subject_counts: Record<string, number>;
}

export interface Progress {
  disclaimer: string;
  topic_status: Record<TopicStatus, number>;
  topics: Topic[];
  subjects: { subject: string; topics: number; answered: number; correct: number; accuracy: number | null }[];
  quiz_history: { quiz_id: string; submitted_at: string; percent: number; questions: number }[];
  activity_30d: { date: string; activities: number }[];
  recent_sessions: StudySessionInfo[];
  revision: RevisionStats;
  totals: { documents: number; conversations: number; quiz_attempts: number };
}

export interface Health {
  status: string;
  version: string;
  auth_mode: "single_user" | "multi_user";
  checks: Record<string, { ok: boolean; detail?: string; [k: string]: unknown }>;
}

export interface SearchResult {
  chunk_id: string;
  document_id: string;
  document_title: string;
  page_number: number;
  page_kind: string;
  section: string | null;
  kind: string;
  text: string;
  score: number;
}

export interface LabelBox { text: string; left: number; top: number; width: number; height: number; conf: number }
