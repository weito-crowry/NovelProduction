import { createServer } from "node:http";
import process from "node:process";

const port = Number(process.argv[process.argv.indexOf("--port") + 1]);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error("--port is required");

const responses = {
  "style.entity_mentions": { mentions: [] },
  "style.term_candidates": { terms: [] },
  "style.speaker_attribution": { speaker_entity_id: null, confidence: 0, evidence_block_ids: [], reason_code: "unknown" },
  "style.pov": { pov_mode: "unclear", pov_entity_id: null, confidence: 0.1 },
  "style.scene_boundary": { boundaries: [] },
  "style.scene_semantics": { function: [{ label: "daily", confidence: 0.9 }], tone: [{ label: "calm", confidence: 0.9 }], pace: { label: "medium", confidence: 0.9 }, information_load: { label: "low", confidence: 0.9 }, interaction: { label: "dialogue", confidence: 0.9 } },
  "style.block_semantic": { label: "description", confidence: 0.9 },
};

const server = createServer(async (request, response) => {
  if (request.method === "GET" && request.url === "/health") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ ok: true }));
    return;
  }
  if (request.method !== "POST" || request.url !== "/chat/completions") {
    response.writeHead(404);
    response.end();
    return;
  }
  let body = "";
  for await (const chunk of request) body += chunk;
  let promptId = "";
  try {
    const payload = JSON.parse(body);
    const system = payload.messages?.find((message) => message.role === "system")?.content ?? "";
    if (system.includes("時間・場所・POV")) promptId = "style.scene_boundary";
    else if (system.includes("人物・組織・場所・技術")) promptId = "style.entity_mentions";
    else if (system.includes("subject_blockのDialogue話者")) promptId = "style.speaker_attribution";
    else if (system.includes("制度・技術・組織名・地名")) promptId = "style.term_candidates";
    else if (system.includes("Scene全体の役割")) promptId = "style.scene_semantics";
    else if (system.includes("対象Narration Block")) promptId = "style.block_semantic";
    else if (system.includes("Sceneの視点形式")) promptId = "style.pov";
    const userContent = payload.messages?.find((message) => message.role === "user")?.content;
    JSON.parse(userContent);
  } catch {
    response.writeHead(400, { "content-type": "application/json" });
    response.end(JSON.stringify({ error: { message: "invalid request" } }));
    return;
  }
  const content = responses[promptId] ?? {};
  response.writeHead(200, { "content-type": "application/json" });
  response.end(JSON.stringify({ choices: [{ message: { content: JSON.stringify(content) } }] }));
});

server.listen(port, "127.0.0.1");
process.once("SIGTERM", () => server.close(() => process.exit(0)));
process.once("SIGINT", () => server.close(() => process.exit(0)));
