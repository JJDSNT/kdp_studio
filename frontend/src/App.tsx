import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { get, type BookOverview, type Info, type SectionEntry } from "./api.ts";
import { go, href, parse, type Route } from "./route.ts";
import {
  BookView, ContinuityView, DocumentsView, EditionsView, GatesView, JobsView, LibraryView, PlanView, ProofsView,
  ReaderView, ResearchView, SectionView, StyleView, TemplatesView, TranslationView, VersionView, useQuery,
} from "./views.tsx";
import type { Navigation } from "./Assistant.tsx";

// CopilotKit is fetched only when the assistant panel opens.
const Assistant = lazy(() => import("./Assistant.tsx"));

function useRoute(fallbackLanguage: string): Route {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const listen = () => setHash(window.location.hash);
    window.addEventListener("hashchange", listen);
    return () => window.removeEventListener("hashchange", listen);
  }, []);
  return parse(hash, fallbackLanguage);
}

export default function App() {
  const info = useQuery(() => get<Info>("/api/info"), []);
  const book = useQuery(() => get<BookOverview>("/api/book"), []);
  const route = useRoute(book.data?.source_language || "");
  const [assistantOpen, setAssistantOpen] = useState(true);
  const onNavigate = useCallback((where: Navigation) => {
    go({ view: where.view, language: where.language, section: where.section, version: where.version,
      document: where.document, tab: where.view === "section" ? "read" : undefined });
    book.reload();
  }, [book.reload]);

  if (book.error) return <p className="problem">{book.error}</p>;
  if (!book.data) return <p className="muted">Opening the book…</p>;
  const data = book.data;
  const language = data.languages[route.language] ? route.language : data.source_language;
  const contents = data.languages[language].contents;
  const assistant = info.data?.assistant;

  return (
    <div className={`room ${assistant && assistantOpen ? "with-assistant" : ""}`}>
      <header>
        <a className="brand" href={href({ view: "book", language })}>KDP Studio</a>
        <a className="book-title" href={href({ view: "library", language })} title="Open another book">
          {data.languages[language].title} ▾</a>
        <nav>
          {(["book", "research", "plan", "style", "continuity", "translation", "gates", "jobs", "editions", "proofs", "reader", "templates", "documents"] as const).map((view) => (
            <a key={view} className={route.view === view ? "active" : ""} href={href({ view, language })}>{view}</a>
          ))}
        </nav>
        <select value={language} onChange={(e) => go({ ...route, language: e.target.value })}>
          {Object.keys(data.languages).map((l) => <option key={l}>{l}</option>)}
        </select>
        {assistant ? (
          <button className="secondary" onClick={() => setAssistantOpen(!assistantOpen)}>
            {assistantOpen ? "Hide assistant" : "Assistant"}
          </button>
        ) : (
          <span className="muted" title={info.data?.assistant_reason}>assistant off</span>
        )}
      </header>
      <aside className="toc">
        {contents.map((entry) =>
          entry.type === "part" ? (
            <div key={entry.id} className="toc-part">
              <p>{entry.kind === "part" ? `Part ${entry.number}` : entry.kind} · {entry.title}</p>
              {entry.sections.map((s) => <TocLink key={s.id} s={s} route={route} language={language} />)}
            </div>
          ) : <TocLink key={entry.id} s={entry} route={route} language={language} />,
        )}
      </aside>
      <main>
        {route.view === "book" && <BookView book={data} language={language} />}
        {route.view === "section" && <SectionView route={{ ...route, language }} onChanged={book.reload} />}
        {route.view === "version" && <VersionView route={route} onChanged={book.reload} />}
        {route.view === "gates" && <GatesView book={data} language={language} onChanged={book.reload} />}
        {route.view === "editions" && <EditionsView language={language} />}
        {route.view === "proofs" && <ProofsView language={language} />}
        {route.view === "documents" && <DocumentsView route={route} />}
        {route.view === "style" && <StyleView language={language} />}
        {route.view === "continuity" && <ContinuityView language={language} />}
        {route.view === "translation" && <TranslationView book={data} language={language} onChanged={book.reload} />}
        {route.view === "jobs" && <JobsView language={language} />}
        {route.view === "reader" && <ReaderView language={language} />}
        {route.view === "templates" && <TemplatesView />}
        {route.view === "library" && <LibraryView />}
        {route.view === "plan" && <PlanView book={data} language={language} onChanged={book.reload} />}
        {route.view === "research" && <ResearchView language={language} />}
      </main>
      {assistant && assistantOpen && (
        <aside className="assistant">
          <Suspense fallback={<p className="muted">Opening the assistant…</p>}>
            <Assistant route={{ ...route, language }} title={data.languages[language].title} book={data.id} onNavigate={onNavigate} />
          </Suspense>
        </aside>
      )}
    </div>
  );
}

function TocLink({ s, route, language }: { s: SectionEntry; route: Route; language: string }) {
  const active = route.section === s.id && (route.view === "section" || route.view === "version");
  return (
    <a className={`toc-link ${active ? "active" : ""}`} href={href({ view: "section", language, section: s.id })}>
      <span className="num">{s.number || "·"}</span> {s.title}
      {s.candidates > 0 && <span className="dot" title={`${s.candidates} candidate version(s)`} />}
      {s.review?.state === "approved" && !s.review.changed_since && <span className="tick" title="approved">✓</span>}
    </a>
  );
}
