import { useCallback, useEffect, useState } from "react";
import Editor from "./Editor.tsx";
import {
  get, openBook, renderTheme, runCommand, type BookOverview, type Catalogue, type EditionState, type EpubSpine, type Finding,
  type Gate, type Info, type LibraryBook, type Section, type SectionEntry, type Theme, type TranslationReport, type VersionReport,
} from "./api.ts";
import { go, href, type Route } from "./route.ts";

/** Load a query, and load it again when `deps` change or `reload` is called. */
export function useQuery<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    setError("");
    load().then((value) => live && setData(value)).catch((e: Error) => live && setError(e.message));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, error, reload: useCallback(() => setTick((t) => t + 1), []) };
}

function Problem({ text }: { text: string }) {
  return text ? <p className="problem">{text}</p> : null;
}

function when(iso?: string): string {
  return iso ? new Date(iso).toLocaleString() : "";
}

// ---------------------------------------------------------------- the book

export function BookView({ book, language }: { book: BookOverview; language: string }) {
  const info = book.languages[language];
  const sections = info.contents.flatMap((e) => (e.type === "part" ? e.sections : [e]));
  const words = sections.reduce((sum, s) => sum + s.words, 0);
  const candidates = sections.reduce((sum, s) => sum + s.candidates, 0);
  const waiting = book.gates.filter((g) => g.state === "waiting");
  const reviewed = sections.filter((s) => s.review?.state === "approved" && !s.review.changed_since).length;
  return (
    <div className="page">
      <h1>{info.title}</h1>
      <p className="subtitle">{info.subtitle}</p>
      <p className="meta">{book.author} · {language} · {sections.length} sections · {words.toLocaleString()} words</p>
      <div className="cards">
        <a className="card" href={href({ view: "gates", language })}>
          <strong>{waiting.length}</strong> gate(s) waiting for you
        </a>
        <a className="card" href={href({ view: "editions", language })}>
          <strong>{Object.keys(book.editions).length}</strong> edition(s): build and measure
        </a>
        <div className="card"><strong>{reviewed}/{sections.length}</strong> sections approved as they read now</div>
        <div className="card"><strong>{candidates}</strong> candidate version(s) to read</div>
      </div>
      {!sections.length && (
        <div className="empty">
          <h2>No chapters yet</h2>
          <p>Tell the assistant your idea. It will ask what the book is for and write <code>intentions.md</code> with
            you; then research, a plan of chapters you adopt, and the writer, chapter by chapter.</p>
        </div>
      )}
      <table className="contents">
        <tbody>
          {info.contents.map((entry) =>
            entry.type === "part" ? (
              [<tr key={entry.id} className="part-row"><td colSpan={4}>
                {entry.kind === "part" ? `Part ${entry.number}` : entry.kind} — {entry.title}</td></tr>,
               ...entry.sections.map((s) => <SectionRow key={s.id} s={s} language={language} />)]
            ) : <SectionRow key={entry.id} s={entry} language={language} />,
          )}
        </tbody>
      </table>
    </div>
  );
}

export function ReviewBadge({ review }: { review: SectionEntry["review"] }) {
  if (!review) return <span className="review none">not reviewed</span>;
  if (review.state === "approved" && review.changed_since) return <span className="review changed">changed since approval</span>;
  if (review.state === "approved") return <span className="review approved">approved</span>;
  return <span className="review none">{review.state.replace("_", " ")}</span>;
}

export function TranslationBadge({ state }: { state: string }) {
  const tone = state === "translated" ? "approved" : state === "stale" ? "changed" : "none";
  return <span className={`review ${tone}`}>{state === "stale" ? "source changed since" : state}</span>;
}

function SectionRow({ s, language }: { s: SectionEntry; language: string }) {
  return (
    <tr>
      <td className="num">{s.number || ""}</td>
      <td><a href={href({ view: "section", language, section: s.id })}>{s.title}</a>
        {s.candidates > 0 && <span className="badge">{s.candidates} version(s)</span>}</td>
      <td>{s.translation ? <TranslationBadge state={s.translation} /> : <ReviewBadge review={s.review} />}</td>
      <td className="num">{s.words}</td>
    </tr>
  );
}

// ------------------------------------------------------------- a section

export function SectionView({ route, onChanged }: { route: Route; onChanged: () => void }) {
  const { data, error, reload } = useQuery(
    () => get<Section>("/api/section", { lang: route.language, id: route.section }), [route.language, route.section]);
  const [draft, setDraft] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [status, setStatus] = useState("");
  useEffect(() => { setDraft(null); setStatus(""); }, [route.section, route.language]);
  if (error) return <Problem text={error} />;
  if (!data) return <p className="muted">Loading…</p>;
  const tabs = ["read", "versions", "history", "edit"];
  const dirty = draft !== null && draft !== data.text;

  async function save() {
    try {
      const result = await runCommand<{ changed: boolean }>("save_section", {
        language: data!.language, section: data!.section, text: draft, expected_digest: data!.digest, reason,
      });
      setStatus(result.changed ? "Saved, and committed to the book's history." : "Nothing changed.");
      setDraft(null);
      setReason("");
      reload();
      onChanged();
    } catch (e) {
      setStatus((e as Error).message);
    }
  }

  return (
    <div className="page">
      <p className="meta">{data.kind === "chapter" ? `Chapter ${data.number}` : data.kind} · {data.words} words · {data.section}</p>
      <h1>{data.title}</h1>
      <ChapterPlan language={data.language} section={data.section} empty={!data.text.split(/\n---\n/).slice(1).join("").trim()} />
      <ChapterActions language={data.language} section={data.section} onChanged={() => { reload(); onChanged(); }} />
      <nav className="tabs">
        {tabs.map((tab) => (
          <a key={tab} className={route.tab === tab ? "active" : ""} href={href({ ...route, tab })}>
            {tab === "edit" ? "edit by hand" : tab}{tab === "versions" && data.versions.length ? ` (${data.versions.length})` : ""}
          </a>
        ))}
      </nav>
      <Problem text={data.problem} />
      {route.tab === "read" && (
        <iframe className="preview" title="preview" srcDoc={
          `<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/ebook.css">
          <style>body{max-width:34em;margin:1.5em auto;padding:0 1em}</style></head><body>${data.preview}</body></html>`} />
      )}
      {route.tab === "edit" && (
        <div className="edit">
          <Editor key={data.digest} value={data.text} onChange={setDraft} />
          <div className="savebar">
            <input placeholder="Why this change (goes into the history)" value={reason}
                   onChange={(e) => setReason(e.target.value)} />
            <button disabled={!dirty} onClick={save}>Save</button>
            <span className="muted">{dirty ? "Unsaved changes" : status}</span>
          </div>
        </div>
      )}
      {route.tab === "versions" && (
        data.versions.length ? (
          <ul className="list">
            {data.versions.map((v) => (
              <li key={v.id}>
                <a href={href({ view: "version", language: v.language, section: v.section, version: v.id })}>{v.id}</a>
                <span className={`state ${v.state}`}>{v.state}</span> {v.scope} · {v.rationale}
                <span className="muted"> — {v.proposed_by.id} ({v.proposed_by.kind}), {when(v.proposed_at)}</span>
              </li>
            ))}
          </ul>
        ) : <p className="muted">No versions yet. Ask the assistant for one, or edit the text directly.</p>
      )}
      {route.tab === "history" && (
        <ul className="list">
          {data.history.map((h) => (
            <li key={h.commit}><code>{h.commit}</code> {h.message} <span className="muted">— {h.actor || "git"}, {when(h.at)}</span></li>
          ))}
          {!data.history.length && <li className="muted">No recorded history (the book is not a git repository?).</li>}
        </ul>
      )}
    </div>
  );
}

// --------------------------------------------------------- a version

export function VersionView({ route, onChanged }: { route: Route; onChanged: () => void }) {
  const { data, error, reload } = useQuery(() => get<VersionReport>("/api/version", { id: route.version }), [route.version]);
  const [rationale, setRationale] = useState("");
  const [status, setStatus] = useState("");
  const [whole, setWhole] = useState(false);
  if (error) return <Problem text={error} />;
  if (!data) return <p className="muted">Loading…</p>;
  const facts = [...data.fidelity.facts_removed.map((f) => ["−", ...f]), ...data.fidelity.facts_added.map((f) => ["+", ...f])];

  async function decide(command: "adopt_version" | "reject_version") {
    try {
      await runCommand(command, { version_id: data!.id, rationale });
      setStatus(command === "adopt_version" ? "Adopted: the section now reads like this, and the history says why." : "Rejected, with the reason kept.");
      reload();
      onChanged();
    } catch (e) {
      setStatus((e as Error).message);
    }
  }

  return (
    <div className="page">
      <p className="meta"><a href={href({ view: "section", language: data.language, section: data.section, tab: "versions" })}>{data.section}</a> · {data.language}</p>
      <h1>Version {data.id} <span className={`state ${data.state}`}>{data.state}</span></h1>
      <p><strong>Scope:</strong> {data.scope} · <strong>Why:</strong> {data.rationale}</p>
      <p className="muted">Proposed by {data.proposed_by.id} ({data.proposed_by.kind}), {when(data.proposed_at)}
        {data.decided_by && <> · {data.state} by {data.decided_by.id}{data.decision_rationale ? `: ${data.decision_rationale}` : ""}</>}</p>
      {data.violations.map((v) => <p key={v} className="problem">⚠ {v}</p>)}
      {!data.base_is_current && data.state === "candidate" && (
        <p className="problem">The section changed since this version was proposed; it can no longer be adopted as is.</p>)}
      <div className="fidelity">
        <strong>Fidelity:</strong> {data.fidelity.identical_words ? "no word changed" : "words changed (below)"}
        {facts.length > 0 ? (
          <ul>{facts.map((f, i) => <li key={i} className={f[0] === "+" ? "added" : "removed"}>{f[0]} {f[1]}: <code>{f[2]}</code> ×{f[3]}</li>)}</ul>
        ) : <span> · no number, date, name, URL or code changed</span>}
      </div>
      {data.translation && (
        <div className="fidelity">
          <strong>Against the source:</strong>{" "}
          {data.translation.filter((f) => f.verdict === "pass").length} of {data.translation.length} measurements the same
          <FindingRows findings={data.translation.filter((f) => f.verdict !== "pass")} />
        </div>
      )}
      <label className="toggle"><input type="checkbox" checked={whole} onChange={(e) => setWhole(e.target.checked)} /> Whole text</label>
      <div className="diff">
        {paragraphs(data.diff).map((paragraph, i, all) => {
          const changed = paragraph.some((s) => s.op !== "equal");
          if (!whole && !changed) {
            return all[i - 1] && !all[i - 1].some((s) => s.op !== "equal") ? null
              : <p key={i} className="skipped">⋯</p>;
          }
          const changedChars = paragraph.filter((s) => s.op !== "equal").reduce((n, s) => n + s.text.length, 0);
          const allChars = paragraph.reduce((n, s) => n + s.text.length, 0);
          if (changed && changedChars > 0.4 * allChars) {
            // Rewritten rather than retouched: before and after read better whole.
            const old = paragraph.filter((s) => s.op !== "insert").map((s) => s.text).join("");
            const now = paragraph.filter((s) => s.op !== "delete").map((s) => s.text).join("");
            return (
              <div key={i} className="rewritten">
                {old.trim() && <p><del>{old}</del></p>}
                {now.trim() && <p><ins>{now}</ins></p>}
              </div>
            );
          }
          return (
            <p key={i}>{paragraph.map((segment, j) => (
              segment.op === "equal" ? <span key={j}>{segment.text}</span>
                : segment.op === "delete" ? <del key={j}>{segment.text}</del> : <ins key={j}>{segment.text}</ins>
            ))}</p>
          );
        })}
      </div>
      {data.state === "candidate" && (
        <div className="decide">
          <input placeholder="Your reason (required to reject)" value={rationale} onChange={(e) => setRationale(e.target.value)} />
          <button disabled={!data.base_is_current} onClick={() => decide("adopt_version")}>Adopt</button>
          <button className="secondary" onClick={() => decide("reject_version")}>Reject</button>
        </div>
      )}
      <p className="muted">{status}</p>
    </div>
  );
}

type Segment = VersionReport["diff"][number];

/** The diff, cut into paragraphs, so a long chapter shows only what changed. */
function paragraphs(diff: Segment[]): Segment[][] {
  const out: Segment[][] = [[]];
  for (const segment of diff) {
    const pieces = segment.text.split(/\n{2,}/);
    pieces.forEach((piece, i) => {
      if (i > 0) out.push([]);
      if (piece) out[out.length - 1].push({ op: segment.op, text: piece });
    });
  }
  return out.filter((p) => p.length);
}

// ------------------------------------------------------------- gates

const GATE_KINDS: Record<string, string> = {
  intention: "", material: "", architecture: "", voice: "pilot section id", freeze: "language", publish: "language",
};

export function GatesView({ book, language, onChanged }: { book: BookOverview; language: string; onChanged: () => void }) {
  const [kind, setKind] = useState("intention");
  const [subject, setSubject] = useState("");
  const [rationale, setRationale] = useState<Record<string, string>>({});
  const [status, setStatus] = useState("");

  async function act(command: string, payload: Record<string, unknown>) {
    try {
      await runCommand(command, payload);
      setStatus("");
      onChanged();
    } catch (e) {
      setStatus((e as Error).message);
    }
  }

  return (
    <div className="page">
      <h1>Gates</h1>
      <p className="muted">Each gate records who decided, when, why — and which version was judged. A later version is never approved by an earlier decision.</p>
      <div className="opengate">
        <select value={kind} onChange={(e) => { setKind(e.target.value); setSubject(GATE_KINDS[e.target.value] === "language" ? language : ""); }}>
          {Object.keys(GATE_KINDS).map((k) => <option key={k}>{k}</option>)}
        </select>
        {GATE_KINDS[kind] && <input placeholder={GATE_KINDS[kind]} value={subject} onChange={(e) => setSubject(e.target.value)} />}
        <button onClick={() => act("open_gate", { kind, subject })}>Open gate</button>
      </div>
      <Problem text={status} />
      {[...book.gates].reverse().map((gate: Gate) => (
        <div key={gate.id} className={`gate ${gate.state}`}>
          <p><strong>{gate.kind}</strong> {gate.subject} <span className={`state ${gate.state}`}>{gate.state}</span>
            {gate.changed_since && <span className="badge warn">changed since</span>}</p>
          <p>{gate.question}</p>
          {gate.state === "waiting" ? (
            <div className="decide">
              <input placeholder="Rationale (required for changes or reject)" value={rationale[gate.id] || ""}
                     onChange={(e) => setRationale({ ...rationale, [gate.id]: e.target.value })} />
              {(["approved", "changes_requested", "rejected"] as const).map((decision) => (
                <button key={decision} className={decision === "approved" ? "" : "secondary"}
                        onClick={() => act("decide_gate", { gate_id: gate.id, decision, rationale: rationale[gate.id] || "" })}>
                  {decision === "approved" ? "Approve" : decision === "rejected" ? "Reject" : "Ask for changes"}
                </button>
              ))}
            </div>
          ) : (
            <p className="muted">{gate.decided_by?.id}, {when(gate.decided_at)}{gate.rationale ? ` — ${gate.rationale}` : ""}</p>
          )}
        </div>
      ))}
      {!book.gates.length && <p className="muted">No gate opened yet. The first is usually the intention.</p>}
    </div>
  );
}

// ---------------------------------------------------------- editions

export function EditionsView({ language }: { language: string }) {
  const { data, error, reload } = useQuery(() => get<Record<string, EditionState>>("/api/editions", { lang: language }), [language]);
  const [busy, setBusy] = useState("");
  const [status, setStatus] = useState("");
  if (error) return <Problem text={error} />;
  if (!data) return <p className="muted">Loading…</p>;

  async function act(command: string, edition: string) {
    setBusy(`${command}:${edition}`);
    setStatus("");
    try {
      await runCommand(command, { language, edition });
      if (command === "build") await runCommand("check", { language, edition });
    } catch (e) {
      setStatus((e as Error).message);
    }
    setBusy("");
    reload();
  }

  return (
    <div className="page">
      <h1>Editions — {language}</h1>
      <Problem text={status} />
      {Object.entries(data).map(([edition, state]) => (
        <section key={edition} className="edition">
          <h2>{edition} <span className="muted">template {String(state.settings.template)}</span></h2>
          <p>{state.built ? <><code>{state.built}</code> <span className="muted">built {new Date(state.built_at * 1000).toLocaleString()}</span></> : "not built"}</p>
          <div className="actions">
            <button disabled={!!busy} onClick={() => act("build", edition)}>{busy === `build:${edition}` ? "Building…" : "Build and check"}</button>
            <button className="secondary" disabled={!!busy || !state.built} onClick={() => act("check", edition)}>Check again</button>
            {edition === "print" && state.built && <a href={href({ view: "proofs", language })}>Look at the pages →</a>}
            {edition === "ebook" && state.built && <a href={href({ view: "reader", language })}>Read it →</a>}
          </div>
          {state.images.length > 0 && (
            <div className="covers">
              {state.images.map((name) => (
                <a key={name} href={`/covers/${language}/${name}?t=${state.built_at}`} target="_blank" rel="noreferrer">
                  <img src={`/covers/${language}/${name}?t=${state.built_at}`} alt={name} /></a>))}
            </div>
          )}
          {state.check && (
            <table className="findings">
              <tbody>
                {state.check.findings.map((f) => (
                  <tr key={f.id} className={f.verdict}>
                    <td className="verdict">{f.verdict.replace("_", " ")}</td>
                    <td>{f.item}{f.detail && f.verdict !== "pass" && <div className="muted">{f.detail}</div>}</td>
                    <td>{f.measured}</td>
                    <td className="muted">{f.required}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      ))}
    </div>
  );
}

// ------------------------------------------------------------ proofs

export function ProofsView({ language }: { language: string }) {
  const { data, error } = useQuery(() => get<string[]>("/api/proofs", { lang: language }), [language]);
  const [open, setOpen] = useState("");
  if (error) return <Problem text={error} />;
  if (!data) return <p className="muted">Rasterising the pages…</p>;
  return (
    <div className="page wide">
      <h1>Pages — {language}</h1>
      <p className="muted">{data.length} pages. Look, do not trust the log: a missing label never shows up as an error.</p>
      <div className="proofs">
        {data.map((name, i) => (
          <figure key={name} onClick={() => setOpen(name)}>
            <img loading="lazy" src={`/proofs/${language}/${name}`} alt={`page ${i + 1}`} />
            <figcaption>{i + 1}</figcaption>
          </figure>
        ))}
      </div>
      {open && (
        <div className="lightbox" onClick={() => setOpen("")}>
          <img src={`/proofs/${language}/${open}`} alt={open} />
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------- documents

export function DocumentsView({ route }: { route: Route }) {
  const list = useQuery(() => get<string[]>("/api/documents"), []);
  const doc = route.document || "intentions.md";
  const { data, error } = useQuery(() => get<{ path: string; text: string }>("/api/document", { path: doc }), [doc]);
  return (
    <div className="page split">
      <ul className="doclist">
        {(list.data || []).map((path) => (
          <li key={path} className={path === doc ? "active" : ""}>
            <a href={href({ view: "documents", language: route.language, document: path })}>{path}</a>
          </li>
        ))}
      </ul>
      <div>
        <Problem text={error} />
        {data && <pre className="document">{data.text}</pre>}
      </div>
    </div>
  );
}

export { go };

// --------------------------------------------------------------- style

interface StyleFinding { practice: string; section: string; line: number; excerpt: string; match: string; message: string }
interface StyleReport {
  coverage: { enforced: number; total: number; unenforced: { id: string; rule: string }[] };
  counts: Record<string, number>;
  practices: { id: string; category: string; rule: string; enforced: boolean; source: string }[];
  engines: Record<string, string>;
  findings: StyleFinding[];
}

export function StyleView({ language }: { language: string }) {
  const [engines, setEngines] = useState(false);
  const { data, error } = useQuery(() => get<StyleReport>("/api/style", { lang: language, engines: String(engines) }),
    [language, engines]);
  const [only, setOnly] = useState("");
  if (error) return <Problem text={error} />;
  if (!data) return <p className="muted">{engines ? "Running the catalogue and the open engines…" : "Checking…"}</p>;
  const rules = Object.fromEntries(data.practices.map((p) => [p.id, p]));
  const shown = data.findings.filter((f) => !only || f.practice === only);
  return (
    <div className="page">
      <h1>Style — {language}</h1>
      <p className="muted">{data.coverage.enforced} of {data.coverage.total} practices are enforced by a check.
        Prompts to agents and code are never checked: they are written for a machine.</p>
      <label className="toggle"><input type="checkbox" checked={engines} onChange={(e) => setEngines(e.target.checked)} />
        Also run the open engines (LanguageTool, Vale) configured in style.yaml</label>
      {Object.entries(data.engines).map(([name, state]) => <p key={name} className="muted">{name}: {state}</p>)}
      <div className="chips">
        <button className={only ? "secondary" : ""} onClick={() => setOnly("")}>All ({data.findings.length})</button>
        {Object.entries(data.counts).sort((a, b) => b[1] - a[1]).map(([id, n]) => (
          <button key={id} className={only === id ? "" : "secondary"} onClick={() => setOnly(id)} title={rules[id]?.rule}>
            {id} ({n})</button>
        ))}
      </div>
      {only && rules[only] && <p className="rule">{rules[only].rule}</p>}
      <table className="findings">
        <tbody>
          {shown.map((f, i) => (
            <tr key={i}>
              <td className="verdict">{f.practice}</td>
              <td><a href={href({ view: "section", language, section: f.section, tab: "edit" })}>{f.section}</a>
                <div className="muted">line {f.line}</div></td>
              <td><mark>{f.match}</mark> <span className="muted">{f.excerpt}</span>
                {f.message && <div className="muted">{f.message}</div>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {data.coverage.unenforced.length > 0 && (
        <>
          <h2>Still depends on a reader</h2>
          <ul className="list">{data.coverage.unenforced.map((u) => <li key={u.id}><code>{u.id}</code> {u.rule}</li>)}</ul>
        </>
      )}
    </div>
  );
}

// --------------------------------------------------------- translation

function FindingRows({ findings }: { findings: Finding[] }) {
  if (!findings.length) return null;
  return (
    <table className="findings">
      <tbody>
        {findings.map((f) => (
          <tr key={f.id} className={f.verdict}>
            <td className="verdict">{f.verdict}</td>
            <td>{f.item}</td>
            <td>{f.measured}{f.required && <span className="muted"> (required {f.required})</span>}
              {f.detail && <div className="muted">{f.detail}</div>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function TranslationView({ book, language, onChanged }: { book: BookOverview; language: string; onChanged: () => void }) {
  const source = book.source_language;
  const others = Object.keys(book.languages).filter((l) => l !== source);
  const translated = language !== source;
  const { data, error, reload } = useQuery(
    () => (translated ? get<TranslationReport>("/api/translation", { lang: language }) : Promise.resolve(null)),
    [language, book.revision]);
  const [added, setAdded] = useState("");
  const [status, setStatus] = useState("");

  async function job(kind: string, payload: Record<string, unknown>) {
    setStatus("");
    try {
      await runCommand("start_job", { kind, payload });
      go({ view: "jobs", language });
    } catch (e) {
      setStatus((e as Error).message);
    }
  }

  async function confirm(section: string) {
    const rationale = window.prompt(`Why does the ${language} text of ${section} still correspond to the source?`);
    if (rationale === null) return;
    try {
      await runCommand("confirm_translation", { language, section, rationale });
      reload();
      onChanged();
    } catch (e) {
      setStatus((e as Error).message);
    }
  }

  if (!translated) {
    return (
      <div className="page">
        <h1>Translation</h1>
        <p className="muted">{source} is the language the book is written in. Another language is the same book,
          section by section: the translator adapts each one as a candidate version you read and adopt, and what must
          survive the translation is measured against the source.</p>
        {others.map((l) => (
          <p key={l}><a href={href({ view: "translation", language: l })}>{l} — {book.languages[l].title}</a></p>
        ))}
        <div className="decide">
          <input placeholder="A language to add (en, es, fr…)" value={added} onChange={(e) => setAdded(e.target.value)} />
          <button disabled={!added.trim()} onClick={() => job("add_language", { language: added.trim() })}>Add language</button>
        </div>
        <Problem text={status} />
      </div>
    );
  }
  if (error) return <Problem text={error} />;
  if (!data) return <p className="muted">Measuring the translation against its source…</p>;
  const pending = data.sections.filter((s) => (s.state === "untranslated" || s.state === "stale") && !s.candidates);
  return (
    <div className="page">
      <h1>Translation — {language}</h1>
      <p className="muted">From {data.source_language}. {Object.entries(data.states).map(([state, n]) => `${n} ${state}`).join(", ")}.
        Whether it reads well is yours to judge; what is listed here was measured.</p>
      <p>{data.glossary.present
        ? <>Glossary: {data.glossary.terms} term(s), {data.glossary.keep} name(s) never translated (<code>glossary.yaml</code>).</>
        : <>No <code>glossary.yaml</code> yet: terms are not checked.{" "}
          <button className="secondary" onClick={() => job("propose_glossary", { language })}>Draft the glossary</button></>}</p>
      {pending.length > 0 && (
        <p><button onClick={() => job("translate_book", { language })}>Translate the {pending.length} pending section(s)</button>
          <span className="muted"> Read one translated chapter first: the rest follows its voice.</span></p>
      )}
      <Problem text={status} />
      <FindingRows findings={data.meta.filter((f) => f.verdict !== "pass")} />
      <table className="contents">
        <tbody>
          {data.sections.map((s) => (
            <tr key={s.id}>
              <td className="num">{s.number || ""}</td>
              <td><a href={href({ view: "section", language, section: s.id, tab: s.candidates ? "versions" : "read" })}>{s.title}</a>
                {s.title !== s.source_title && <div className="muted">{s.source_title}</div>}
                {s.candidates > 0 && <span className="badge">{s.candidates} version(s)</span>}
                <FindingRows findings={s.findings.filter((f) => f.verdict !== "pass")} /></td>
              <td><TranslationBadge state={s.state} /></td>
              <td className="num">{s.words ? `${s.words} / ${s.source_words}` : s.source_words}</td>
              <td>
                <button className="secondary" onClick={() => job("translate_section", { language, section: s.id })}>
                  {s.state === "untranslated" ? "Translate" : "Translate again"}</button>
                {(s.state === "stale" || s.state === "unrecorded") && (
                  <button className="secondary" onClick={() => confirm(s.id)}>Still corresponds</button>)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------- continuity

interface Repetition {
  passage: string; words: number; sections: number; span: number;
  occurrences: { section: string; number: number; title: string; paragraph: string }[];
}

export function ContinuityView({ language }: { language: string }) {
  const { data, error } = useQuery(() => get<Repetition[]>("/api/continuity", { lang: language }), [language]);
  if (error) return <Problem text={error} />;
  if (!data) return <p className="muted">Reading the whole book…</p>;
  return (
    <div className="page">
      <h1>Continuity — {language}</h1>
      <p className="muted">Passages that recur in different sections. A template line may be deliberate; a sentence
        repeated eighteen chapters apart is usually a seam. The book is read at once, not chapter by chapter.</p>
      {data.map((r, i) => (
        <div key={i} className="gate">
          <p><strong>{r.sections}×</strong> <span className="muted">{r.words} words, chapters {r.span} apart</span></p>
          <p className="passage">“{r.passage}”</p>
          <p className="muted">{r.occurrences.map((o, j) => (
            <span key={o.section}>{j > 0 && " · "}<a href={href({ view: "section", language, section: o.section })}>
              {o.number ? `ch. ${o.number}` : o.section}</a></span>))}</p>
        </div>
      ))}
      {!data.length && <p className="muted">No passage recurs.</p>}
    </div>
  );
}

// ---------------------------------------------------------------- jobs

interface Job {
  waiting?: { title: string; can_review: boolean; reviewed: boolean; verdict: string; message: string } | null;
  id: string; kind: string; state: string; created_at: string; payload: Record<string, string>;
  progress: { at: string; message: string }[]; result: Record<string, unknown> | null; error: string;
  requested_by: { id: string; kind: string };
}

export function JobsView({ language }: { language: string }) {
  const { data, error, reload } = useQuery(() => get<Job[]>("/api/jobs"), []);
  const running = (data || []).some((j) => j.state === "running" || j.state === "queued");
  const [words, setWords] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState("");

  async function answer(id: string, action: string) {
    setProblem("");
    try {
      const response = await fetch("/api/jobs/answer", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, action, instruction: words[id] || "" }),
      });
      if (!response.ok) throw new Error((await response.json())?.error?.message || response.statusText);
      setWords({ ...words, [id]: "" });
    } catch (e) {
      setProblem((e as Error).message);
    }
    reload();
  }
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(reload, 2000);
    return () => clearInterval(timer);
  }, [running, reload]);
  if (error) return <Problem text={error} />;
  if (!data) return <p className="muted">Loading…</p>;
  return (
    <div className="page">
      <h1>Jobs</h1>
      <Problem text={problem} />
      <p className="muted">Agent work that takes longer than a chat turn. A job writes into the book only when it
        finishes, and only through commands: a candidate version, never the text itself.</p>
      {data.map((job) => (
        <div key={job.id} className={`gate ${job.state === "done" ? "approved" : job.state === "running" || job.state === "waiting" ? "waiting" : ""}`}>
          <p><strong>{job.kind}</strong> {job.payload.section} <span className={`state ${job.state}`}>{job.state}</span>
            <span className="muted"> — {job.requested_by.id} ({job.requested_by.kind}), {when(job.created_at)}</span></p>
          {job.progress.length > 0 && <p className="muted">{job.progress[job.progress.length - 1].message}</p>}
          {job.error && <p className="problem">{job.error}</p>}
          {(((job.result?.reviews || job.result?.critiques) as { verdict: string; overall: string }[] | undefined) || []).map((r, i) => (
            <p key={i} className="muted"><span className={`state ${r.verdict === "accept" ? "approved" : "waiting"}`}>
              {r.verdict}</span> {r.overall}</p>))}
          {job.state === "waiting" && job.waiting && (
            <div className="held">
              <p>{job.waiting.message}</p>
              <div className="decide">
                <input placeholder={job.waiting.reviewed ? "What to change (empty: answer the criticism)" : "What to change"}
                  value={words[job.id] || ""} onChange={(e) => setWords({ ...words, [job.id]: e.target.value })} />
                {job.waiting.can_review && (
                  <button className="secondary" onClick={() => answer(job.id, "critique")}>
                    {job.waiting.reviewed ? "Critique again" : "Critique"}</button>)}
                <button className="secondary" disabled={!job.waiting.reviewed && !(words[job.id] || "").trim()}
                  onClick={() => answer(job.id, "redo")}>Redo</button>
                <button onClick={() => answer(job.id, "done")}>Close</button>
              </div>
            </div>
          )}
          {job.result && (
            <p>{String(job.result.summary || "")}{" "}
              {job.result.version ? <a href={href({ view: "version", language: job.payload.language || language,
                section: job.payload.section, version: String(job.result.version) })}>Compare version {String(job.result.version)} →</a> : null}
              {Array.isArray(job.result.violations) && job.result.violations.length > 0 &&
                <span className="problem"> ⚠ {(job.result.violations as string[]).join("; ")}</span>}
              {Array.isArray(job.result.translated) && (job.result.translated as { section: string; version: string }[]).map((t) => (
                <span key={t.version}> <a href={href({ view: "version", language: job.payload.language || language,
                  section: t.section, version: t.version })}>{t.section} →</a></span>))}
              {job.kind === "run_agent" && job.result.path ? <a href={href({ view: "documents", language, document: String(job.result.path) })}>Read the report →</a> : null}
              {job.kind === "create_agent" ? <> <a href={href({ view: "agents", language })}>Agents →</a></> : null}
              {["design_theme", "revise_theme", "critique_theme"].includes(job.kind) ? <> <a href={href({ view: "templates", language })}>Gallery →</a></> : null}
              {job.kind.startsWith("translate") || job.kind === "add_language" || job.kind === "propose_glossary"
                ? <> <a href={href({ view: "translation", language: job.payload.language || language })}>Translation →</a></> : null}</p>
          )}
        </div>
      ))}
      {!data.length && <p className="muted">No jobs yet. Start one from a section (“Review voice”) or ask the assistant.</p>}
    </div>
  );
}

export function ReviewVoiceButton({ language, section }: { language: string; section: string }) {
  const [status, setStatus] = useState("");
  async function start() {
    try {
      await runCommand("start_job", { kind: "revise_voice", payload: { language, section } });
      go({ view: "jobs", language });
    } catch (e) {
      setStatus((e as Error).message);
    }
  }
  return <><button className="secondary" onClick={start}>Review voice</button>{status && <span className="problem"> {status}</span>}</>;
}

function ChapterActions({ language, section, onChanged }: { language: string; section: string; onChanged: () => void }) {
  const book = useQuery(() => get<BookOverview>("/api/book"), [section]);
  const [instruction, setInstruction] = useState("");
  const [scope, setScope] = useState("content");
  const [status, setStatus] = useState("");
  const entry = book.data?.languages[language]?.contents
    .flatMap((e) => (e.type === "part" ? e.sections : [e])).find((s) => s.id === section);

  async function act(command: string, payload: Record<string, unknown>, then?: () => void) {
    setStatus("");
    try {
      await runCommand(command, payload);
      book.reload();
      onChanged();
      then?.();
    } catch (e) {
      setStatus((e as Error).message);
    }
  }

  return (
    <div className="chapter-actions">
      <div className="actions">
        {entry && <ReviewBadge review={entry.review} />}
        <button onClick={() => act("approve_chapter", { section })}>Approve chapter as it reads now</button>
        <ReviewVoiceButton language={language} section={section} />
      </div>
      <div className="ask">
        <input placeholder="Ask the reviser: “tighten the opening”, “move the example to the end”…" value={instruction}
               onChange={(e) => setInstruction(e.target.value)} />
        <select value={scope} onChange={(e) => setScope(e.target.value)}>
          <option value="wording">wording</option><option value="content">content</option><option value="structure">structure</option>
        </select>
        <button className="secondary" disabled={!instruction.trim()} onClick={() => act("start_job",
          { kind: "revise_section", payload: { language, section, instruction, scope } }, () => go({ view: "jobs", language }))}>Revise</button>
      </div>
      {status && <p className="problem">{status}</p>}
    </div>
  );
}

function ChapterPlan({ language, section, empty }: { language: string; section: string; empty: boolean }) {
  const book = useQuery(() => get<BookOverview>("/api/book"), [section]);
  const [status, setStatus] = useState("");
  const entry = book.data?.languages[language]?.contents
    .flatMap((e) => (e.type === "part" ? e.sections : [e])).find((s) => s.id === section);
  async function write() {
    try {
      await runCommand("start_job", { kind: "write_section", payload: { language, section } });
      go({ view: "jobs", language });
    } catch (e) {
      setStatus((e as Error).message);
    }
  }
  if (!entry) return null;
  return (
    <div className="plan-box">
      {entry.synopsis && <p><strong>Covers</strong> {entry.synopsis}</p>}
      {entry.promise && <p><strong>Promise</strong> {entry.promise}</p>}
      <button className={empty ? "" : "secondary"} onClick={write}>{empty ? "Write this chapter" : "Rewrite with the writer"}</button>
      {status && <span className="problem"> {status}</span>}
    </div>
  );
}

// ---------------------------------------------------------------- plan

interface PlanChapter { title: string; synopsis: string; promise: string; research: string[] }
interface Plan {
  id: string; state: string; proposed_at: string; instruction: string;
  plan: { rationale: string; front: { title: string; synopsis: string }[];
    parts: { title: string; guiding_case: string; chapters: PlanChapter[] }[]; gaps: string[] };
}

export function PlanView({ book, language, onChanged }: { book: BookOverview; language: string; onChanged: () => void }) {
  const { data, error, reload } = useQuery(() => get<Plan[]>("/api/plans"), []);
  const [status, setStatus] = useState("");
  const hasChapters = book.languages[language].contents.length > 0;
  if (error) return <Problem text={error} />;
  if (!data) return <p className="muted">Loading…</p>;
  const latest = data[0];
  async function adopt() {
    try {
      await runCommand("adopt_plan", { plan_id: latest.id });
      onChanged();
      reload();
      go({ view: "book", language });
    } catch (e) {
      setStatus((e as Error).message);
    }
  }
  if (!latest) return <div className="page"><h1>Plan</h1><p className="muted">No plan yet. Ask the assistant for one.</p></div>;
  return (
    <div className="page">
      <h1>Plan <span className={`state ${latest.state}`}>{latest.state}</span></h1>
      <p className="muted">Proposed by the architect, {when(latest.proposed_at)}{latest.instruction ? ` — “${latest.instruction}”` : ""}</p>
      <p>{latest.plan.rationale}</p>
      {latest.plan.front.map((f) => <p key={f.title}><strong>{f.title}</strong> — <span className="muted">{f.synopsis}</span></p>)}
      {latest.plan.parts.map((part, i) => (
        <section key={i} className="plan-part">
          <h2>Part {i + 1} — {part.title}</h2>
          {part.guiding_case && <p className="muted">Guiding case: {part.guiding_case}</p>}
          <ol>
            {part.chapters.map((c) => (
              <li key={c.title}><strong>{c.title}</strong>
                <div>{c.synopsis}</div>
                <div className="promise">→ {c.promise}</div>
                {c.research.length > 0 && <div className="muted">research: {c.research.join(", ")}</div>}
              </li>
            ))}
          </ol>
        </section>
      ))}
      {latest.plan.gaps.length > 0 && <><h2>Gaps</h2><ul className="list">{latest.plan.gaps.map((g) => <li key={g}>{g}</li>)}</ul></>}
      {latest.state === "candidate" && (
        hasChapters
          ? <p className="muted">The book already has chapters: ask the assistant to add, remove or move them following this plan.</p>
          : <div className="actions"><button onClick={adopt}>Adopt plan: create these chapters</button></div>
      )}
      <Problem text={status} />
    </div>
  );
}

// ------------------------------------------------------------ research

interface Source { url: string; title: string; opened: string; says: string; dossier: string; publisher?: string }

export function ResearchView({ language }: { language: string }) {
  const sources = useQuery(() => get<Source[]>("/api/sources"), []);
  const docs = useQuery(() => get<string[]>("/api/documents"), []);
  const dossiers = (docs.data || []).filter((d) => d.startsWith("research/"));
  return (
    <div className="page">
      <h1>Research</h1>
      <p className="muted">Every source was opened by the researcher, on the date shown. A source never opened is not here.</p>
      <h2>Dossiers</h2>
      <ul className="list">
        {dossiers.map((d) => <li key={d}><a href={href({ view: "documents", language, document: d })}>{d}</a></li>)}
        {!dossiers.length && <li className="muted">None yet. Ask the assistant to research something.</li>}
      </ul>
      <h2>Sources ({(sources.data || []).length})</h2>
      <table className="findings"><tbody>
        {(sources.data || []).map((s) => (
          <tr key={s.url}>
            <td className="verdict">{s.opened}</td>
            <td><a href={s.url} target="_blank" rel="noreferrer">{s.title}</a>{s.publisher && <span className="muted"> — {s.publisher}</span>}
              <div className="muted">{s.says}</div></td>
            <td className="muted">{s.dossier}</td>
          </tr>
        ))}
      </tbody></table>
    </div>
  );
}

// -------------------------------------------------------------- library

export function LibraryView() {
  const info = useQuery(() => get<Info>("/api/info"), []);
  const { data, error } = useQuery(() => get<LibraryBook[]>("/api/library"), []);
  const [status, setStatus] = useState("");
  if (error) return <Problem text={error} />;
  if (!data) return <p className="muted">Looking for books…</p>;

  async function open(path: string) {
    try {
      await openBook(path);
      // Everything on the page belongs to the book that was open: start again.
      window.location.assign("/");
    } catch (e) {
      setStatus((e as Error).message);
    }
  }

  return (
    <div className="page">
      <h1>Library</h1>
      <p className="muted">The books in <code>{info.data?.library}</code>. A book is a directory with a <code>book.yaml</code>;
        one is open at a time, and work already running on another goes on. A new book starts with <code>kdp new</code>.</p>
      <Problem text={status} />
      {data.map((b) => (
        <div key={b.path} className={`gate ${b.open ? "approved" : ""}`}>
          <p><strong>{b.title}</strong>{b.author && <span className="muted"> — {b.author}</span>}
            {b.open && <span className="badge">open</span>}</p>
          <p className="muted"><code>{b.path}</code>
            {b.languages && <> · {b.languages.join(", ")} · {b.sections} sections · {(b.words || 0).toLocaleString()} words</>}</p>
          {b.problem && <p className="problem">{b.problem}</p>}
          {!b.open && !b.problem && <button onClick={() => open(b.path)}>Open</button>}
        </div>
      ))}
    </div>
  );
}

// ------------------------------------------------------------ templates

const PAGE_ROLES: [string, string][] = [["part", "Part opening"], ["chapter", "Chapter opening"],
  ["callouts", "Callouts"], ["exercise", "Exercise"]];

export function TemplatesView({ language, onChanged }: { language: string; onChanged: () => void }) {
  const [medium, setMedium] = useState<"print" | "ebook">("print");
  const [ink, setInk] = useState("color");
  const [eink, setEink] = useState(false);
  const themes = useQuery(() => get<Theme[]>("/api/gallery", { lang: language, ink }), [language, ink]);
  const catalogue = useQuery(() => get<Catalogue>("/api/templates"), []);
  const [rendering, setRendering] = useState("");
  const [status, setStatus] = useState("");
  const [zoom, setZoom] = useState("");
  const pending = themes.data?.find((t) => !t.render)?.name || "";

  // One theme at a time: each render runs LuaLaTeX over the specimen.
  useEffect(() => {
    if (!pending || rendering) return;
    setRendering(pending);
    renderTheme(pending, language, ink)
      .catch((e: Error) => setStatus(`${pending}: ${e.message}`))
      .finally(() => { setRendering(""); themes.reload(); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, language, ink]);

  const [draft, setDraft] = useState({ name: "", brief: "", based_on: "nocturne", reference: "" });

  async function design() {
    try {
      await runCommand("start_job", { kind: "design_theme", payload: { ...draft, name: draft.name.trim(), language } });
      go({ view: "jobs", language });
    } catch (e) {
      setStatus((e as Error).message);
    }
  }

  async function job(kind: string, payload: Record<string, unknown>) {
    try {
      await runCommand("start_job", { kind, payload });
      go({ view: "jobs", language });
    } catch (e) {
      setStatus((e as Error).message);
    }
  }

  function revise(theme: string, criticised: boolean) {
    const instruction = window.prompt(criticised
      ? `What should the designer change in “${theme}”? Leave empty to answer the critic's last criticism.`
      : `What should the designer change in “${theme}”?`, "");
    if (instruction === null || (!criticised && !instruction.trim())) return;
    job("revise_theme", { theme, instruction, language });
  }

  async function use(theme: string) {
    const reason = window.prompt(`Take the theme “${theme}” for this book? Say why, for the book's history.`, "");
    if (reason === null) return;
    try {
      await runCommand("set_theme", { theme, reason });
      themes.reload();
      catalogue.reload();
      onChanged();
      setStatus(`The book now uses ${theme}. Build the editions again to see it on your own text.`);
    } catch (e) {
      setStatus((e as Error).message);
    }
  }

  if (themes.error) return <Problem text={themes.error} />;
  if (!themes.data) return <p className="muted">Loading the themes…</p>;
  return (
    <div className="page gallery">
      <h1>Themes</h1>
      <p className="muted">Each theme applied to the same sample text, so a design is chosen by looking: the print
        interior, the cover and the ebook. Taking a theme changes one name per edition in <code>book.yaml</code>; your
        text is not touched, and you can come back.</p>
      <div className="chips">
        <button className={medium === "print" ? "" : "secondary"} onClick={() => setMedium("print")}>Print</button>
        <button className={medium === "ebook" ? "" : "secondary"} onClick={() => setMedium("ebook")}>Ebook</button>
        <span className="apart" />
        {medium === "print" ? (
          <>
            <button className={ink === "color" ? "" : "secondary"} onClick={() => setInk("color")}>Colour</button>
            <button className={ink === "black" ? "" : "secondary"} onClick={() => setInk("black")}
              title="A black-and-white interior costs less to print; the cover stays in colour">Black ink</button>
          </>
        ) : (
          <>
            <button className={eink ? "secondary" : ""} onClick={() => setEink(false)}>Colour screen</button>
            <button className={eink ? "" : "secondary"} onClick={() => setEink(true)}>E-ink</button>
          </>
        )}
      </div>
      {medium === "print" && ink === "black" && (
        <p className="muted">The interior in black ink only: every colour becomes the grey the theme chose, or its
          luminance. To print the book this way, write <code>ink: black</code> under <code>editions.print</code> in
          <code> book.yaml</code>; the check then fails any page that still carries colour.</p>)}
      <Problem text={status} />
      {themes.data.map((theme) => {
        const print = theme.kinds[medium] || theme.kinds.print || theme.kinds.ebook || theme.kinds.cover;
        const base = theme.render ? `/gallery/${theme.render.key}` : "";
        return (
          <section key={theme.name} className={`theme ${theme.in_use ? "in-use" : ""}`}>
            <div className="theme-head">
              <h2>{theme.title} <code>{theme.name}</code>
                {theme.in_use ? <span className="badge">used by this book</span>
                  : theme.used_by.length > 0 && <span className="badge">used for {theme.used_by.join(", ")}</span>}</h2>
              {!theme.in_use && <button onClick={() => use(theme.name)}>Use this theme</button>}
            </div>
            <p>{print.description}</p>
            <p className="muted">{Object.keys(theme.kinds).join(" · ")} · {theme.source}
              {print.fonts.length > 0 && <> · {print.fonts.join(", ")}</>}
              {theme.designed_by && <> · drawn by the {theme.designed_by} over {theme.based_on}</>}</p>
            {theme.brief && <p className="muted">Brief: “{theme.brief}”</p>}
            {(theme.inspired_by || []).map((r) => (
              <p key={r.url} className="muted">Looked at <a href={r.url} target="_blank" rel="noreferrer">{r.title || r.url}</a>
                {" "}({r.license || "no licence stated"}): {r.taken}</p>))}
            {Object.keys(print.colors).length > 0 && (
              <p className="swatches">{Object.entries(print.colors).map(([name, value]) => (
                <span key={name} title={`${name} #${value}`} style={{ background: `#${value}` }} />))}</p>
            )}
            <div className="actions">
              <button className="secondary" onClick={() => job("critique_theme", { theme: theme.name, language })}>
                {theme.critique ? "Ask the critic again" : "Ask the critic"}</button>
              {theme.revisable && (
                <button className="secondary" onClick={() => revise(theme.name, !!theme.critique)}>Revise…</button>)}
            </div>
            {theme.critique && (
              <details className="critique" open={theme.critique.verdict !== "accept"}>
                <summary><span className={`state ${theme.critique.verdict === "accept" ? "approved" : "waiting"}`}>
                  critic: {theme.critique.verdict}</span> {theme.critique.defects} defect(s),{" "}
                  {theme.critique.problems.length} remark(s) · {when(theme.critique.at)}</summary>
                <p>{theme.critique.overall}</p>
                <p className="muted"><strong>Character.</strong> {theme.critique.character}</p>
                {theme.critique.answers_the_brief && (
                  <p className="muted"><strong>The brief.</strong> {theme.critique.answers_the_brief}</p>)}
                <table className="findings">
                  <tbody>
                    {theme.critique.problems.map((p, i) => (
                      <tr key={i} className={p.severity === "defect" ? "fail" : p.severity === "weakness" ? "warn" : ""}>
                        <td className="verdict">{p.severity}</td>
                        <td>{p.where}{p.owner && p.owner !== "designer" && (
                          <div className="muted">for the {p.owner === "art" ? "art director" : "template"}</div>)}</td>
                        <td>{p.what} <span className="muted">{p.why}</span><div className="muted">→ {p.fix}</div></td>
                      </tr>))}
                  </tbody>
                </table>
                {theme.critique.strengths.length > 0 && (
                  <p className="muted"><strong>Keep.</strong> {theme.critique.strengths.join(" · ")}</p>)}
              </details>
            )}
            {!theme.render ? (
              <p className="muted">{rendering === theme.name ? "Rendering over the sample text…" : "Waiting to be rendered…"}</p>
            ) : medium === "ebook" ? (
              <div className="strip">
                {theme.render.cover && (
                  <figure onClick={() => setZoom(`${base}/${theme.render!.cover}`)}>
                    <img src={`${base}/${theme.render.cover}`} alt="cover" style={{ filter: eink ? "grayscale(1)" : "none" }} />
                    <figcaption>Cover</figcaption></figure>)}
                {theme.render.ebook.filter((f) => !f.includes("praefatio")).map((file) => (
                  <figure key={file} className="ebook">
                    <iframe title={`${theme.name} ${file}`} src={`${base}/epub/${file}`}
                      style={{ filter: eink ? "grayscale(1)" : "none" }} />
                    <figcaption>{file.startsWith("part-") ? "Part opening" : file.includes("exercitium") ? "Exercise and prompt" : "Chapter, callouts"}</figcaption>
                  </figure>))}
                {!theme.kinds.ebook && <p className="muted">This theme has no ebook.</p>}
              </div>
            ) : (
              <div className="strip">
                {theme.render.cover && (
                  <figure onClick={() => setZoom(`${base}/${theme.render!.cover}`)}>
                    <img src={`${base}/${theme.render.cover}`} alt="cover" /><figcaption>Cover</figcaption></figure>)}
                {PAGE_ROLES.map(([role, label]) => {
                  const page = theme.render!.pages.find((p) => p.role === role);
                  return page ? (
                    <figure key={role} onClick={() => setZoom(`${base}/${page.file}`)}>
                      <img className="paper" src={`${base}/${page.file}`} alt={label} /><figcaption>{label}</figcaption></figure>
                  ) : null;
                })}
                {theme.render.wrap && (
                  <figure className="wide" onClick={() => setZoom(`${base}/${theme.render!.wrap}`)}>
                    <img src={`${base}/${theme.render.wrap}`} alt="print wrap" /><figcaption>Print wrap</figcaption></figure>)}
                {!theme.kinds.print && <p className="muted">This theme has no print interior.</p>}
              </div>
            )}
          </section>
        );
      })}
      <section className="theme">
        <h2>A new theme</h2>
        <p className="muted">The designer draws one from your brief, starting from a theme that exists and, if you
          point at one, from a page on the web: it takes the design, records the address and its licence, and copies
          code only when the licence allows. The result is built over the sample text; only if it builds does it
          join this gallery.</p>
        <div className="decide">
          <input placeholder="name (lowercase)" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          <select value={draft.based_on} onChange={(e) => setDraft({ ...draft, based_on: e.target.value })}>
            {themes.data.map((t) => <option key={t.name} value={t.name}>from {t.name}</option>)}
          </select>
        </div>
        <div className="decide">
          <input placeholder="Brief: what the book is, and how its page should feel" value={draft.brief}
            onChange={(e) => setDraft({ ...draft, brief: e.target.value })} />
        </div>
        <div className="decide">
          <input placeholder="A web page to look at (optional)" value={draft.reference}
            onChange={(e) => setDraft({ ...draft, reference: e.target.value })} />
          <button disabled={!draft.name.trim() || !draft.brief.trim()} onClick={design}>Draw it</button>
        </div>
      </section>
      {zoom && <div className="zoom" onClick={() => setZoom("")}><img src={zoom} alt="" /></div>}
      {catalogue.data && (
        <>
          <h2>Publishers</h2>
          <p className="muted">What a publisher or printer asks of a cover: the sizes come from here and from the book's
            trim, never from the theme. A book may bring its own in <code>publishers/&lt;name&gt;.yaml</code>.</p>
          {catalogue.data.publishers.map((p) => (
            <div key={p.name} className={`gate ${p.in_use ? "approved" : ""}`}>
              <p><strong>{p.title}</strong> <code>{p.name}</code> <span className="muted">{p.source}</span>
                {p.in_use && <span className="badge">used by this book</span>}</p>
              <p className="muted">bleed {p.bleed}″ · spine per page {Object.entries(p.spine_per_page).map(([k, v]) => `${k} ${v}″`).join(", ")}
                {" "}· spine text from {p.spine_text_pages} pages · barcode {p.barcode.join(" × ")}″ · ebook cover {p.ebook_pixels.join(" × ")} px · {p.dpi} dpi</p>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- reader

const DEVICES: Record<string, { label: string; width: number; ink: boolean }> = {
  phone: { label: "Phone", width: 360, ink: false },
  ereader: { label: "E-reader (e-ink)", width: 560, ink: true },
  tablet: { label: "Tablet", width: 820, ink: false },
};

export function ReaderView({ language }: { language: string }) {
  const { data, error } = useQuery(() => get<EpubSpine>("/api/epub", { lang: language }), [language]);
  const [at, setAt] = useState(0);
  const [device, setDevice] = useState("ereader");
  useEffect(() => setAt(0), [language]);
  if (error) return <div className="page"><h1>Reader — {language}</h1><Problem text={error} />
    <p><a href={href({ view: "editions", language })}>Build the ebook in Editions →</a></p></div>;
  if (!data) return <p className="muted">Opening the ebook…</p>;
  const page = data.spine[Math.min(at, data.spine.length - 1)];
  const shape = DEVICES[device];
  return (
    <div className="page reader">
      <h1>Reader — {language}</h1>
      <p className="muted"><code>{data.file}</code>, built {new Date(data.built_at * 1000).toLocaleString()}. These are the
        ebook's own files in its reading order, at a reader's width; a real reader still chooses the font and may drop
        colours, so check on a device before publishing.</p>
      <div className="chips">
        {Object.entries(DEVICES).map(([id, d]) => (
          <button key={id} className={device === id ? "" : "secondary"} onClick={() => setDevice(id)}>{d.label}</button>))}
        <button className="secondary" disabled={at === 0} onClick={() => setAt(at - 1)}>← Previous</button>
        <select value={at} onChange={(e) => setAt(Number(e.target.value))}>
          {data.spine.map((item, i) => <option key={item.href} value={i}>{item.title || item.href}</option>)}
        </select>
        <button className="secondary" disabled={at >= data.spine.length - 1} onClick={() => setAt(at + 1)}>Next →</button>
      </div>
      <div className="device" style={{ width: shape.width }}>
        <iframe key={page.href} title={page.title} src={`/epub/${language}/${page.href}?t=${data.built_at}`}
          style={{ filter: shape.ink ? "grayscale(1)" : "none" }} />
      </div>
    </div>
  );
}

// --------------------------------------------------------------- publish

export function PublishView({ book, language }: { book: BookOverview; language: string }) {
  const { data, error } = useQuery(() => get<Record<string, EditionState>>("/api/editions", { lang: language }), [language]);
  if (error) return <Problem text={error} />;
  if (!data) return <p className="muted">Loading…</p>;
  const decided = (kind: string, subject: string) =>
    book.gates.filter((g) => g.kind === kind && g.subject === subject).slice(-1)[0];
  const frozen = decided("freeze", language);
  const isFrozen = frozen?.state === "approved" && !frozen.changed_since;
  const sections = book.languages[language].contents.flatMap((e) => (e.type === "part" ? e.sections : [e]));
  const untranslated = sections.filter((s) => s.translation && s.translation !== "translated").length;
  const rows: { item: string; ok: boolean; note: string; to?: string }[] = [];
  if (language !== book.source_language) {
    rows.push({ item: "Translation", ok: untranslated === 0, to: href({ view: "translation", language }),
      note: untranslated ? `${untranslated} of ${sections.length} sections not translated, or stale` : "every section translated from the current source" });
  }
  rows.push({ item: "Text frozen", ok: isFrozen, to: href({ view: "gates", language }),
    note: isFrozen ? `frozen by ${frozen.decided_by?.id}` : frozen?.changed_since ? "the text changed after it was frozen" : `no freeze gate approved for ${language}` });
  for (const [edition, state] of Object.entries(data)) {
    const counts = state.check?.summary || {};
    const fails = counts.fail || 0;
    rows.push({ item: `${edition} built and measured`, ok: !!state.built && !!state.check && fails === 0,
      to: href({ view: "editions", language }),
      note: !state.built ? "not built" : !state.check ? "built, not measured"
        : `${state.built} — ${Object.entries(counts).map(([k, v]) => `${v} ${k.replace("_", " ")}`).join(", ")}` });
  }
  for (const edition of Object.keys(data).filter((e) => e !== "cover")) {
    const gate = decided("publish", `${language}/${edition}`) || decided("publish", language);
    rows.push({ item: `Decision to publish the ${edition} edition`, ok: gate?.state === "approved" && !gate.changed_since,
      to: href({ view: "gates", language }), note: gate ? `${gate.state}${gate.changed_since ? ", but the files changed since" : ""}` : "no publish gate decided" });
  }
  const ready = rows.every((r) => r.ok);
  return (
    <div className="page">
      <h1>Readiness — {language}</h1>
      <p className="muted">What stands between this language and the publisher, read from the book's own records. The order
        matters: freeze the text, build and measure the interior, then the cover (every page changes its spine), then decide.</p>
      <table className="findings">
        <tbody>
          {rows.map((r) => (
            <tr key={r.item} className={r.ok ? "pass" : "warn"}>
              <td className="verdict">{r.ok ? "ready" : "open"}</td>
              <td>{r.to ? <a href={r.to}>{r.item}</a> : r.item}</td>
              <td className="muted">{r.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>{ready ? "Everything measured here is ready." : "Not ready yet: the open lines above say what is missing."}</p>
      <p className="muted">KDP Studio does not upload: the files go to the publisher's site by hand. They are in <code>builds/{language}/</code>; the metadata package (categories, keywords,
        description) is not generated yet.</p>
    </div>
  );
}

// ---------------------------------------------------------------- agents

interface AgentManifest {
  id: string; title: string; role: string; works_on: string; reads: string[]; output: string; web: boolean;
  source: string; system: string; origin: { created_by?: string; brief?: string };
}

const IN_CODE: [string, string][] = [
  ["researcher", "searches the web and records every source it opened"], ["architect", "proposes parts and chapters"],
  ["writer", "writes a chapter to its promise"], ["reviser", "changes a section as you instruct"],
  ["voice reviser", "fixes register and form"], ["translator", "adapts a section into another language"],
  ["designer", "draws a theme"], ["critic", "judges a theme's rendered pages"],
];

export function AgentsView({ book, language }: { book: BookOverview; language: string }) {
  const { data, error } = useQuery(() => get<AgentManifest[]>("/api/agents"), []);
  const sections = book.languages[language].contents.flatMap((e) => (e.type === "part" ? e.sections : [e]));
  const [section, setSection] = useState("");
  const [instruction, setInstruction] = useState("");
  const [draft, setDraft] = useState({ id: "", brief: "" });
  const [status, setStatus] = useState("");
  if (error) return <Problem text={error} />;
  if (!data) return <p className="muted">Loading…</p>;
  const chosen = section || sections[0]?.id || "";

  async function start(kind: string, payload: Record<string, unknown>) {
    setStatus("");
    try {
      await runCommand("start_job", { kind, payload });
      go({ view: "jobs", language });
    } catch (e) {
      setStatus((e as Error).message);
    }
  }

  return (
    <div className="page">
      <h1>Agents</h1>
      <p className="muted">Specialists you put to work on a section or on the whole book. A <em>report</em> changes
        nothing and is kept under Documents; <em>edits</em> become a candidate version you compare and adopt. None of
        them decides a gate, and none has a tool: they read the book and answer.</p>
      <div className="decide">
        <select value={chosen} onChange={(e) => setSection(e.target.value)}>
          {sections.map((s) => <option key={s.id} value={s.id}>{s.number ? `${s.number}. ` : ""}{s.title}</option>)}
        </select>
        <input placeholder="An instruction for the agent (optional)" value={instruction}
          onChange={(e) => setInstruction(e.target.value)} />
      </div>
      <Problem text={status} />
      {data.map((agent) => (
        <div key={agent.id} className="gate">
          <p><strong>{agent.title}</strong> <code>{agent.id}</code> <span className="muted">{agent.source}</span>
            <span className="badge">{agent.output}</span>{agent.web && <span className="badge">reads the web</span>}</p>
          <p>{agent.role}</p>
          <p className="muted">Works on {agent.works_on === "section" ? "one section" : "the whole book"} · reads{" "}
            {agent.reads.join(", ")}{agent.origin?.created_by && <> · created by the {agent.origin.created_by}</>}</p>
          <details><summary className="muted">Its instructions</summary><p className="muted">{agent.system}</p></details>
          <div className="actions">
            <button onClick={() => start("run_agent", { agent: agent.id, language,
              section: agent.works_on === "section" ? chosen : "", instruction })}>
              {agent.works_on === "section" ? "Run on this section" : "Run on the book"}</button>
          </div>
        </div>
      ))}
      <h2>In code</h2>
      <p className="muted">These need more than a manifest can declare (measurements, a build, a search) and are started
        from where they act: a chapter, the Translation and Themes views, or the assistant.</p>
      <ul className="list">{IN_CODE.map(([name, what]) => <li key={name}><strong>{name}</strong> — {what}</li>)}</ul>
      <section className="theme">
        <h2>A new agent</h2>
        <p className="muted">The meta-agent designs one from your brief, out of what the others are made of: what it
          may read, and a report or edits. It is tried once on this book before it joins the catalogue.</p>
        <div className="decide">
          <input placeholder="id (lowercase)" value={draft.id} onChange={(e) => setDraft({ ...draft, id: e.target.value })} />
          <input placeholder="What it should do, and for what" value={draft.brief}
            onChange={(e) => setDraft({ ...draft, brief: e.target.value })} />
          <button disabled={!draft.id.trim() || !draft.brief.trim()}
            onClick={() => start("create_agent", { id: draft.id.trim(), brief: draft.brief, language, section: chosen })}>
            Create it</button>
        </div>
      </section>
    </div>
  );
}
