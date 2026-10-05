import { useCallback, useEffect, useState } from "react";
import Editor from "./Editor.tsx";
import {
  get, runCommand, type BookOverview, type EditionState, type Gate, type Section, type VersionReport,
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
        <div className="card"><strong>{candidates}</strong> candidate version(s) to read</div>
      </div>
      <table className="contents">
        <tbody>
          {info.contents.map((entry) =>
            entry.type === "part" ? (
              [<tr key={entry.id} className="part-row"><td colSpan={3}>
                {entry.kind === "part" ? `Part ${entry.number}` : entry.kind} — {entry.title}</td></tr>,
               ...entry.sections.map((s) => <SectionRow key={s.id} s={s} language={language} />)]
            ) : <SectionRow key={entry.id} s={entry} language={language} />,
          )}
        </tbody>
      </table>
    </div>
  );
}

function SectionRow({ s, language }: { s: { id: string; number: number; title: string; words: number; candidates: number }; language: string }) {
  return (
    <tr>
      <td className="num">{s.number || ""}</td>
      <td><a href={href({ view: "section", language, section: s.id })}>{s.title}</a>
        {s.candidates > 0 && <span className="badge">{s.candidates} version(s)</span>}</td>
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
  const tabs = ["read", "edit", "versions", "history"];
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
      <nav className="tabs">
        {tabs.map((tab) => (
          <a key={tab} className={route.tab === tab ? "active" : ""} href={href({ ...route, tab })}>
            {tab}{tab === "versions" && data.versions.length ? ` (${data.versions.length})` : ""}
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
      <label className="toggle"><input type="checkbox" checked={whole} onChange={(e) => setWhole(e.target.checked)} /> Whole text</label>
      <div className="diff">
        {paragraphs(data.diff).map((paragraph, i, all) => {
          const changed = paragraph.some((s) => s.op !== "equal");
          if (!whole && !changed) {
            return all[i - 1] && !all[i - 1].some((s) => s.op !== "equal") ? null
              : <p key={i} className="skipped">⋯</p>;
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
          </div>
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
