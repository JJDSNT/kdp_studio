# ADR 0019: Agents as manifests, the agents the specification names, and a meta-agent

Status: accepted (2026-10-10).

## Context

Eight agents existed, each a Python module, and the specification names a
dozen more. The author wants every agent ready and an agent that can create
agents — and asked whether an agent loses quality by being a manifest.

## Decision

- **An agent whose whole job is to read and to answer is a manifest**
  (`agents/manifest.py`; YAML in `agent_manifests/`, the person's
  `$XDG_DATA_HOME/kdp-studio/agents/`, a book's `agents/`): a role, whether it
  works on a section or the book, the *readers* it uses from a fixed list
  (the section, the plan, the whole text, research, sources, glossary, style
  findings, recurring passages, meta, editorial documents, the archive,
  gates, art), whether it may read the web, a system prompt, optional
  *knowledge notes*, and one of two outputs.
- **Two outputs, each landing the only way it can.** A *report* — summary,
  argued body, findings with a severity, and what could not be established —
  is kept as a dated document under `reports/` through the `add_report`
  command and changes nothing else. *Edits* go through the boundary every
  reviser uses (ADR 0009): refused on prompts, code and frontmatter, recorded
  as a candidate version under a declared scope, audited for fidelity.
- **Shipped as manifests**: interviewer, fact-checker, technical reviewer,
  experimenter, continuity reviser (edits), intention guardian, ingestor,
  diagnostician, mapper, KDP packager, marketer, art director, reader of the
  translation. The art director owns the cover picture and the
  illustrations; the critic of themes now knows it, and knows what the
  designer controls: each of its problems names an owner (designer, template,
  art), and only the designer's count against a theme or reach the designer.
- **In code stay the agents that need more than reading**: researcher (a
  ledger), architect and writer (stubs, plans), revisers, translator (measured
  against its source), designer (assembled and built), critic (shown pictures).
- **The meta-agent** (`agents/meta.py`) designs a manifest from a brief, out
  of the readers and the two outputs, with a knowledge note when the role
  rests on facts. The manifest is parsed against the same rules as any other
  and *tried once* on the book — a report shown and not kept; edits are never
  tried on the author's text — before it joins the person's catalogue. It
  cannot widen the boundary: whatever it writes, the new agent reads the book
  and reports or proposes.

## Does a manifest cost quality?

Not where quality comes from the prompt, the context and the model: a
manifest agent is given the same intention, voice and text as a coded one,
and answers in the same structured shape. It costs what code adds: a check
written for that one role (the translator's count of numbers and prompt ids),
a loop (the designer rebuilding until the specimen compiles), a record of its
own (the researcher's ledger). So the rule is the one above: read-and-answer
in a manifest, measure-and-build in code — and when a manifest agent turns
out to need a measurement, that is the sign to move it.

## Consequences

- The experimenter cannot run anything and says so: it writes the protocol.
  The ingestor reads text files only; converting Word or PDF is not done.
- A report is advice in a file; nothing yet turns its findings into tasks.

## Validation

Real model on a copy of *A Era dos Agentes*: the intention guardian on
chapter 4 in 56 s — a verdict ("diverges in the exercise"), six findings
quoting the passages, and one thing it could not establish (the plan gives
this chapter no promise). The meta-agent designed, tried and catalogued an
"opening in a scene" checker in 61 s; its trial said, correctly, that the
section it was tried on is a preface.
