// Where the room is, kept in the address so a reload, a link or the assistant
// can put the author anywhere.

export type View = "book" | "section" | "version" | "gates" | "editions" | "proofs" | "documents" | "style"
  | "continuity" | "jobs" | "plan" | "research" | "translation"
  | "reader" | "templates" | "library" | "publish";

export interface Route {
  view: View;
  language: string;
  section: string;
  version: string;
  document: string;
  tab: string;
}

const VIEWS: View[] = ["book", "section", "version", "gates", "editions", "proofs", "documents", "style",
  "continuity", "jobs", "plan", "research", "translation", "reader",
  "templates", "library", "publish"];

/** The views by stage of the work, in the order a book goes through them. */
export const STAGES: { id: string; label: string; views: View[] }[] = [
  { id: "write", label: "Plan & write", views: ["book", "research", "plan", "documents"] },
  { id: "review", label: "Review", views: ["style", "continuity", "translation"] },
  { id: "produce", label: "Produce", views: ["templates", "editions", "proofs", "reader"] },
  { id: "publish", label: "Publish", views: ["publish"] },
];

export const VIEW_LABELS: Partial<Record<View, string>> = {
  book: "Chapters", plan: "Plan", documents: "Documents", editions: "Editions & cover", proofs: "Print pages",
  reader: "Ebook reader", publish: "Readiness",
};

export function stageOf(view: View): string {
  // A chapter and its versions are where writing happens.
  if (view === "section" || view === "version") return "write";
  return STAGES.find((stage) => stage.views.includes(view))?.id || "";
}

export function parse(hash: string, fallbackLanguage: string): Route {
  const query = new URLSearchParams(hash.replace(/^#\/?/, ""));
  const view = query.get("view") as View;
  return {
    view: VIEWS.includes(view) ? view : "book",
    language: query.get("lang") || fallbackLanguage,
    section: query.get("section") || "",
    version: query.get("version") || "",
    document: query.get("doc") || "",
    tab: query.get("tab") || "read",
  };
}

export function href(route: Partial<Route>): string {
  const pairs: Record<string, string> = {};
  if (route.view) pairs.view = route.view;
  if (route.language) pairs.lang = route.language;
  if (route.section) pairs.section = route.section;
  if (route.version) pairs.version = route.version;
  if (route.document) pairs.doc = route.document;
  if (route.tab && route.tab !== "read") pairs.tab = route.tab;
  return `#/${new URLSearchParams(pairs)}`;
}

export function go(route: Partial<Route>): void {
  window.location.hash = href(route);
}
