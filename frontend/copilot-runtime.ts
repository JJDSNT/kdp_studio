// The Copilot Runtime: the open path between CopilotKit in the page and the
// Python assistant over AG-UI. `kdp serve --assistant` starts and supervises
// it, and proxies /api/copilotkit to it, so the page talks to one origin.
import { createServer } from "node:http";
import { HttpAgent } from "@ag-ui/client";
import { CopilotRuntime, InMemoryAgentRunner } from "@copilotkit/runtime/v2";
import { createCopilotNodeListener } from "@copilotkit/runtime/v2/node";

const port = Number(process.env.KDP_COPILOT_PORT || 8789);
const agentUrl = process.env.KDP_ASSISTANT_URL || "http://127.0.0.1:8788/";

const runtime = new CopilotRuntime({
  agents: { assistant: new HttpAgent({ url: agentUrl }) },
  runner: new InMemoryAgentRunner(),
});

// A dropped connection from the agent must not take the runtime down.
process.on("uncaughtException", (error) => console.error("copilot runtime:", error.message));
process.on("unhandledRejection", (error) => console.error("copilot runtime:", String(error)));

createServer(createCopilotNodeListener({ runtime, basePath: "/api/copilotkit" }))
  .listen(port, "127.0.0.1", () => console.log(`copilot runtime on ${port}`));
