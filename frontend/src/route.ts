// Where the room is, kept in the address so a reload, a link or the assistant
// can put the author anywhere.

export type View = "book" | "section" | "version" | "gates" | "editions" | "proofs" | "documents" | "style"
  | "continuity" | "jobs" | "plan" | "research" | "translation";

export interface Route {
  view: View;
  language: string;
  section: string;
  version: string;
  document: string;
  tab: string;
}

const VIEWS: View[] = ["book", "section", "version", "gates", "editions", "proofs", "documents", "style",
  "continuity", "jobs", "plan", "research", "translation"];

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
