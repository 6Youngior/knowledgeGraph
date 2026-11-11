import assert from "node:assert/strict";
import http from "node:http";
import { once } from "node:events";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import { createJiti } from "jiti";

const here = dirname(fileURLToPath(import.meta.url));
const extensionPath = resolve(here, "..", "extensions", "fingraph.ts");
const stubPath = join(here, "fixtures", "open.mjs");
const jiti = createJiti(import.meta.url, { alias: { open: stubPath } });
const extension = await jiti.import(extensionPath);
const openModule = await jiti.import(stubPath);

const health = { mode: "ok" };
const server = http.createServer((req, res) => {
  if (req.url !== "/api/health") {
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ detail: "not found" }));
    return;
  }
  if (health.mode === "error") {
    res.writeHead(503, { "content-type": "application/json" });
    res.end(JSON.stringify({ detail: "service unavailable" }));
    return;
  }
  res.writeHead(200, { "content-type": "application/json" });
  res.end(JSON.stringify({ status: "ok", llm_available: false }));
});
server.listen(0, "127.0.0.1");
await once(server, "listening");
const base = `http://127.0.0.1:${server.address().port}`;

let state;
let ctx;
let notices;

process.env.FINGRAPH_AS_OF = "2026-11-11";

function makeContext() {
  state = { commands: {}, tools: [], events: {}, ui: {} };
  notices = [];
  const pi = {
    on(event, handler) { (state.events[event] ??= []).push(handler); },
    registerCommand(name, definition) { state.commands[name] = definition; },
    registerTool(definition) { state.tools.push(definition.name); },
  };
  extension.default(pi);
  ctx = {
    mode: "tui",
    cwd: process.cwd(),
    model: { name: "DeepSeek V4.1 Flash" },
    ui: {
      notify(message, type) { notices.push({ message, type }); },
      setHeader(factory) { state.ui.headerFactory = factory; },
      setTitle(title) { state.ui.title = title; },
      setStatus(key, text) { state.ui.status = { key, text }; },
    },
  };
  return pi;
}

async function startSession() {
  assert.ok(state.events.session_start?.[0], "session_start handler missing");
  await state.events.session_start[0]({}, ctx);
}

test.after(() => {
  server.close();
});

test("brand header and command surface", async () => {
  makeContext();
  await startSession();
  const header = state.ui.headerFactory({}, { fg: (_color, text) => text }).render(120).join("\n");
  assert.match(header, /FinGraphAgent/);
  assert.match(header, /0\.2\.0/);
  assert.match(header, /股票事件研究/);
  assert.match(header, /DeepSeek V4\.1 Flash/);
  assert.match(header, /2026-11-11/);
  assert.match(header, /\/web/);
  assert.match(header, /\/model/);
  assert.match(header, /\/usage/);
  assert.doesNotMatch(header, /1\.5\.2/);
  assert.deepEqual(Object.keys(state.commands), ["web"]);
  assert.ok(!state.commands.help);
  assert.ok(!state.commands.usage);
  assert.ok(!state.commands.time);
  assert.deepEqual(state.tools, []);
  assert.equal(state.ui.title, "FinGraphAgent · 股票事件研究");
});

test("/web --no-open checks health without opening", async () => {
  makeContext();
  process.env.FINGRAPH_WEB_URL = base;
  process.env.FINGRAPH_AS_OF = "2026-11-11";
  openModule.calls.length = 0;
  await state.commands.web.handler("--no-open", ctx);
  assert.equal(notices.at(-1).type, "info");
  assert.match(notices.at(-1).message, /研究服务正常/);
  assert.equal(openModule.calls.length, 0);
});

test("/web opens the configured URL with wait:false", async () => {
  makeContext();
  process.env.FINGRAPH_WEB_URL = base;
  openModule.calls.length = 0;
  await state.commands.web.handler("", ctx);
  assert.equal(notices.at(-1).type, "info");
  assert.match(notices.at(-1).message, /已打开研究网页/);
  assert.deepEqual(openModule.calls, [{ url: base, options: { wait: false } }]);
});

test("/web opens the event returned by the latest successful graph query", async () => {
  makeContext();
  process.env.FINGRAPH_WEB_URL = base;
  openModule.calls.length = 0;
  await state.events.tool_execution_end[0]({
    toolName: "mcp__fingraph__related_stocks", isError: false,
    result: { content: [{ type: "text", text: JSON.stringify({ found: true, event: { id: "event:glm5-release" } }) }] },
  }, ctx);
  await state.commands.web.handler("", ctx);
  assert.equal(new URL(openModule.calls[0].url).searchParams.get("event"), "event:glm5-release");
});

test("health failure is reported", async () => {
  makeContext();
  process.env.FINGRAPH_WEB_URL = base;
  health.mode = "error";
  openModule.calls.length = 0;
  await state.commands.web.handler("--no-open", ctx);
  health.mode = "ok";
  assert.equal(notices.at(-1).type, "warning");
  assert.match(notices.at(-1).message, /HTTP 503/);
  assert.equal(openModule.calls.length, 0);
});

test("URL and argument validation", async () => {
  makeContext();
  process.env.FINGRAPH_WEB_URL = "file:///tmp/page.html";
  await state.commands.web.handler("--no-open", ctx);
  assert.equal(notices.at(-1).type, "error");
  assert.match(notices.at(-1).message, /http/);

  process.env.FINGRAPH_WEB_URL = base;
  await state.commands.web.handler("--url https://example.com", ctx);
  assert.equal(notices.at(-1).type, "error");
  assert.match(notices.at(-1).message, /--no-open/);

  delete process.env.FINGRAPH_WEB_URL;
  await state.commands.web.handler("--no-open", ctx);
  assert.equal(notices.at(-1).type, "error");
  assert.match(notices.at(-1).message, /FINGRAPH_WEB_URL/);
});
