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
  review: { gate: string; state: string; changed_since: boolean; decided_at: string } | null;
  synopsis: string;
  promise: string;
  /** In a translated language: untranslated, translated, stale or unrecorded. */
  translation: string | null;
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
  /** A version in a translated language, measured against its source. */
  translation?: Finding[];
}

export interface Finding {
  id: string;
  item: string;
  verdict: string;
  measured: string;
  required: string;
  detail: string;
}

export interface TranslationReport {
  language: string;
  source_language: string;
  glossary: { present: boolean; terms: number; keep: number };
  meta: Finding[];
  sections: {
    id: string; number: number; kind: string; title: string; source_title: string; state: string;
    candidates: number; words: number; source_words: number; findings: Finding[]; summary: Record<string, number>;
  }[];
  states: Record<string, number>;
  summary: Record<string, number>;
}

export interface EditionState {
  settings: Record<string, unknown>;
  built: string;
  built_at: number;
  /** For a cover: the pictures to look at. */
  images: string[];
  check: { target: string; findings: Finding[]; summary: Record<string, number> } | null;
}

export interface LibraryBook {
  path: string; open: boolean; id: string; title: string; author?: string; languages?: string[];
  sections?: number; words?: number; problem?: string;
}

export interface Catalogue {
  templates: {
    name: string; kind: string; title: string; description: string; source: string; origin: string;
    fonts: string[]; colors: Record<string, string>; trims: string[]; in_use: boolean;
  }[];
  publishers: {
    name: string; title: string; source: string; bleed: number; spine_per_page: Record<string, number>;
    spine_text_pages: number; barcode: number[]; ebook_pixels: number[]; dpi: number; in_use: boolean;
  }[];
  editions: Record<string, Record<string, unknown>>;
  overrides: Record<string, string>;
}

export interface Theme {
  name: string; title: string; source: string; in_use: boolean; used_by: string[];
  designed_by?: string; brief?: string; based_on?: string;
  inspired_by?: { url: string; title: string; license: string; taken: string }[];
  kinds: Record<string, { description: string; source: string; fonts: string[]; colors: Record<string, string>; origin: string }>;
  render: null | {
    key: string; pages: { file: string; role: string }[]; cover: string; wrap: string; ebook: string[];
  };
}

export interface EpubSpine {
  file: string; built_at: number; cover: string; spine: { href: string; title: string }[];
}

export interface Info {
  path: string;
  library: string;
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

/** Open another book of the library: not a change to any book, so not a command. */
export function openBook(path: string): Promise<{ book: string; path: string }> {
  return fetch("/api/open", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) })
    .then((r) => json<{ book: string; path: string }>(r));
}

/** Render a theme over the specimen: a cache, not a change to any book. */
export function renderTheme(theme: string, language: string, ink = "color"): Promise<unknown> {
  return fetch("/api/gallery/build", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ theme, language, ink }),
  }).then((r) => json<unknown>(r));
}
