// The control room reads queries and sends every change as a command
// (POST /api/commands). No component writes the book's files.

export interface Gate {
  id: string;
  kind: string;
  subject: string;
  question: string;
  state: string;
  requested_at: string;
  decided_at?: string;
  decided_by?: { id: string; kind: string };
  rationale?: string;
  changed_since: boolean;
}

export interface SectionEntry {
  type: "section";
  id: string;
  kind: string;
  number: number;
  title: string;
  toc_title: string;
  words: number;
  candidates: number;
}

export interface PartEntry {
  type: "part";
  id: string;
  kind: string;
  number: number;
  title: string;
  sections: SectionEntry[];
}

export interface BookOverview {
  id: string;
  author: string;
  source_language: string;
  languages: Record<string, { title: string; subtitle: string; contents: (SectionEntry | PartEntry)[] }>;
  editions: Record<string, Record<string, unknown>>;
  revision: number;
  gates: Gate[];
}

export interface Version {
  id: string;
  language: string;
  section: string;
  state: string;
  scope: string;
  rationale: string;
  task: string;
  proposed_at: string;
  proposed_by: { id: string; kind: string };
  decided_by?: { id: string; kind: string };
  decision_rationale?: string;
}

export interface Section {
  language: string;
  section: string;
  text: string;
  digest: string;
  title: string;
  number: number;
  kind: string;
  words: number;
  preview: string;
  problem: string;
  versions: Version[];
  history: { commit: string; at: string; message: string; actor: string }[];
}

export interface VersionReport extends Version {
  base_is_current: boolean;
  diff: { op: "equal" | "delete" | "insert"; text: string }[];
  fidelity: {
    ok: boolean;
    identical_words: boolean;
    facts_added: [string, string, number][];
    facts_removed: [string, string, number][];
  };
  violations: string[];
}

export interface Finding {
  id: string;
  item: string;
  verdict: string;
  measured: string;
  required: string;
  detail: string;
}

export interface EditionState {
  settings: Record<string, unknown>;
  built: string;
  built_at: number;
  check: { target: string; findings: Finding[]; summary: Record<string, number> } | null;
}

export interface Info {
  book: string;
  assistant: boolean;
  assistant_reason: string;
  person: { id: string; kind: string };
}

export class ApiError extends Error {}

async function json<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(body?.error?.message || `${response.status} ${response.statusText}`);
  return body as T;
}

export const get = <T,>(path: string, params: Record<string, string> = {}): Promise<T> => {
  const query = new URLSearchParams(params).toString();
  return fetch(query ? `${path}?${query}` : path).then((r) => json<T>(r));
};

export function runCommand<T = Record<string, unknown>>(command: string, payload: Record<string, unknown>): Promise<T> {
  return fetch("/api/commands", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command, payload }),
  })
    .then((r) => json<{ result: T }>(r))
    .then((body) => body.result);
}
