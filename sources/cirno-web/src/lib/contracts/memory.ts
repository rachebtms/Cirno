/** Memory library records and bounded evidence pages returned by instance actions. */
export type MemoryLayer = "all" | "event" | "knowledge" | "task" | "source" | "profile";
export type MemoryScope = "all" | "user" | "project" | "session";
export type MemorySearchMode = "bm25" | "semantic" | "hybrid";
export type MemoryTimeField = "observed_at" | "created_at" | "updated_at";
export interface MemoryRecord {
  id: string;
  title: string;
  source: string;
  scope: string;
  layer: string;
  kind: string;
  revision: number;
  status: string;
  tags: string[];
  updated_at: string;
  owner_title?: string;
  project_id?: string;
  session_key?: string;
  observed_at?: string | null;
  created_at?: string;
  snippet?: string;
}
export interface MemoryDocument extends MemoryRecord {
  content: string;
  links: { source: string; target: string; relation: string; evidence: string }[];
}
export interface MemoryStatus {
  counts: Record<string, number>;
  pending: number;
  failed: number;
  index_bytes: number;
  databases?: Record<string, number>;
  receipts?: { memory_id: string; outcome: string; reason: string; input_revision: number }[];
  last_consolidation?: { at: string; status: string; error?: string | null } | null;
  consolidation_failed?: number;
  consolidation_failures?: { source: string; error: string | null; at: string }[];
  last_dream: {
    at: string;
    error?: string;
    created?: number;
    merged?: number;
    skipped?: number;
    retained?: number;
  } | null;
  failures?: { memory_id: string; revision: number; attempts: number; error: string | null }[];
}
export interface MemorySearchResult {
  memories: MemoryRecord[];
  has_more: boolean;
  next_offset: number;
  time_zone?: string;
  engine?: MemorySearchMode;
  warning_code?: string;
  warning?: string;
  embedding_index_pending?: boolean;
  links?: MemoryLink[];
  links_truncated?: boolean;
}
export interface MemoryLink { source: string; target: string; relation: string }
export interface EvidenceReference {
  id: string;
  revision?: number;
  start_line?: number;
  char_offset?: number;
}
export interface EvidenceCursor extends EvidenceReference {
  revision: number;
}
export interface EvidencePage {
  memory_id: string;
  revision: number;
  source: string;
  content?: string;
  note?: string;
  source_refs?: { memory_id?: string; source?: string; revision?: number; start_line?: number }[];
  lines?: { line: number; text: string; char_offset?: number; next_char_offset: number | null }[];
  next_line?: number | null;
}
export interface MemoryQuery {
  query: string;
  tags: string;
  mode: MemorySearchMode;
  layer: MemoryLayer;
  scope: MemoryScope;
  since: string;
  until: string;
  timeField: MemoryTimeField;
  includeHistory: boolean;
}
