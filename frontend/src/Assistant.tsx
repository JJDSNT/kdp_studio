// The editorial assistant: a LangGraph CoAgent through CopilotKit (ADR 0002).
//
// The page tells the agent what the author is looking at (useAgentContext).
// The agent can take the screen somewhere (shared state: it only moves the
// view), and asks here before it writes anything into the book (interrupt).
import { useEffect, useRef } from "react";
import { CopilotChat, CopilotKitProvider, useAgent, useAgentContext, useInterrupt } from "@copilotkit/react-core/v2";
import "@copilotkit/react-core/v2/styles.css";
import type { Route } from "./route.ts";

export interface Navigation {
  view: Route["view"];
  language: string;
  section: string;
  version: string;
  document: string;
  id: string;
}

interface Props {
  route: Route;
  title: string;
  onNavigate: (where: Navigation) => void;
}

function threadId(): string {
  const key = "kdp-studio:assistant-thread";
  try {
    const known = sessionStorage.getItem(key);
    if (known) return known;
    const made = `thread-${Math.random().toString(36).slice(2, 10)}`;
    sessionStorage.setItem(key, made);
    return made;
  } catch {
    return "thread-default";
  }
}

const FOLLOWED = new Set<string>();

function readMessage(value: unknown): string {
  if (typeof value === "string") {
    try { return readMessage(JSON.parse(value)); } catch { return value; }
  }
  if (value && typeof value === "object" && "message" in value) return String((value as { message: unknown }).message);
  return "";
}

function Conversation({ route, title, onNavigate, thread }: Props & { thread: string }) {
  useAgentContext({ description: "View", value: route.view });
  useAgentContext({ description: "Language", value: route.language });
  useAgentContext({ description: "Section", value: route.section || "none" });
  useAgentContext({ description: "Section tab", value: route.view === "section" ? route.tab : "none" });
  useAgentContext({ description: "Version", value: route.version || "none" });
  useAgentContext({ description: "Document", value: route.document || "none" });
  useAgentContext({ description: "Book", value: title });
  const { agent } = useAgent({ agentId: "assistant" });
  const where = (agent?.state as { navigate?: Navigation } | undefined)?.navigate;
  useEffect(() => {
    // Follow each request once: the thread outlives a reload.
    if (!where?.id || FOLLOWED.has(where.id)) return;
    FOLLOWED.add(where.id);
    onNavigate(where);
  }, [where, onNavigate]);
  useInterrupt({
    agentId: "assistant",
    render: (props) => {
      const { resolve } = props;
      const standard = (props as { interrupt?: { message?: string } }).interrupt;
      const message = standard?.message || readMessage((props as { event?: { value?: unknown } }).event?.value) || "Confirmar?";
      return (
        <div className="assistant-confirm">
          <p>{message}</p>
          <button type="button" onClick={() => resolve({ approved: true })}>Sim</button>
          <button type="button" className="secondary" onClick={() => resolve({ approved: false })}>Não</button>
        </div>
      );
    },
  });
  return <CopilotChat agentId="assistant" threadId={thread} />;
}

export default function Assistant(props: Props) {
  const thread = useRef(threadId()).current;
  return (
    // The development inspector fetches from outside the machine: off.
    <CopilotKitProvider runtimeUrl="/api/copilotkit" enableInspector={false}>
      <Conversation {...props} thread={thread} />
    </CopilotKitProvider>
  );
}
