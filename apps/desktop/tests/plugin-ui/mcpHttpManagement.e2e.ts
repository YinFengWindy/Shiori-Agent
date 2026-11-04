import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { resolve } from "node:path";
import { DevelopmentApp } from "./packagedDevelopmentApp";
import { Evidence, record } from "./packagedEvidence";
import { eventually } from "./packagedApp";

const repository = resolve(import.meta.dirname, "../../../..");
await mkdir(resolve(repository, ".test-tmp-root"), { recursive: true });
const output = await mkdtemp(resolve(repository, ".test-tmp-root/mcp-http-management-"));
const workspace = resolve(output, "workspace"), profile = resolve(output, "profile");
await mkdir(workspace); await mkdir(profile);
await writeFile(resolve(workspace, "config.toml"), '[llm]\nregistrations=[]\n[plugins.memory_optimizer]\nenabled=false\n[plugins.desktop_pet]\nenabled=false\n[plugins.mcp]\nenabled=false\n', "utf8");
const token = "private-http-fixture-secret";
const targets: string[] = [];
const peer = createServer((request, response) => {
  void (async () => {
    targets.push(request.url ?? "");
    response.setHeader("content-type", "application/json");
    if (request.headers.authorization !== `Bearer ${token}` && request.headers["x-api-key"] !== token) {
      response.writeHead(401); response.end(JSON.stringify({ error: token })); return;
    }
    if (request.method !== "POST") { response.writeHead(request.method === "DELETE" ? 200 : 405); response.end(); return; }
    let body = "";
    for await (const chunk of request) body += String(chunk);
    const rpc = record(JSON.parse(body));
    if (!("id" in rpc)) { response.writeHead(202); response.end(); return; }
    const result = rpc.method === "server/discover" ? { error: { code: -32601, message: "Unknown method" } }
      : rpc.method === "initialize" ? { result: { protocolVersion: "2025-11-25", capabilities: { tools: {} }, serverInfo: { name: "fixture", version: "1" } } }
      : { result: { tools: ["echo", "other"].map((name) => ({ name, description: name, inputSchema: { type: "object" } })) } };
    response.setHeader("mcp-session-id", "fixture");
    response.end(JSON.stringify({ jsonrpc: "2.0", id: rpc.id, ...result }));
  })().catch(() => { response.writeHead(500); response.end(); });
});
await new Promise<void>((ready) => peer.listen(0, "127.0.0.1", ready));
const address = peer.address();
assert.ok(address && typeof address !== "string");
const url = `http://127.0.0.1:${address.port}/mcp?filter=read&key=query-private-canary`;
const executable = resolve(repository, "apps/desktop/node_modules/electron/dist", process.platform === "win32" ? "electron.exe" : "electron");
const app = new DevelopmentApp({ executable, workspace, profile }, new Evidence(output), "development");
const snapshot = async () => app.call("mcp.servers.list");
const rows = async () => { const value = await snapshot(); assert.ok(Array.isArray(value.servers)); return value.servers.map(record); };
const connected = async () => eventually(rows, (servers) => servers.length === 1 && servers[0].status === "connected", "connected HTTP server");
const select = async (name: string, option: string) => {
  await app.page!.getByRole("combobox", { name, exact: true }).click();
  await app.page!.getByRole("option", { name: option, exact: true }).click();
};
try {
  await app.launch(); await app.settings();
  await app.page!.getByRole("switch", { name: "启用 MCP", exact: true }).click();
  await app.page!.getByRole("button", { name: "MCP 设置", exact: true }).click();
  let page = app.page!;
  await eventually(() => page.getByRole("button", { name: "添加服务器", exact: true }).isEnabled(), Boolean, "MCP management ready");
  await page.getByRole("button", { name: "添加服务器", exact: true }).click();
  await page.getByRole("textbox", { name: "服务器 ID", exact: true }).fill("http_fixture");
  await page.getByRole("textbox", { name: "显示名称", exact: true }).fill("HTTP Fixture");
  await select("连接方式", "Streamable HTTP");
  await page.getByLabel("服务器地址", { exact: true }).fill(url);
  await select("认证方式", "Bearer");
  await page.getByLabel("Bearer token", { exact: true }).fill(token);
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await connected();
  await app.evidence.add("http-bearer-discovery", await snapshot());
  await page.getByRole("button", { name: "编辑 HTTP Fixture", exact: true }).click();
  await select("工具选择模式", "选择工具");
  await page.getByRole("checkbox", { name: "echo", exact: true }).check();
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await page.getByRole("button", { name: "测试连接", exact: true }).click();
  await eventually(rows, (servers) => record(servers[0].operation).kind === "test" && record(servers[0].operation).status === "succeeded", "HTTP probe");
  await page.getByRole("button", { name: "编辑 HTTP Fixture", exact: true }).click();
  await select("Bearer token 编辑方式", "替换");
  await page.getByLabel("Bearer token", { exact: true }).fill("invalid-token");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await eventually(rows, (servers) => servers[0].status === "error" && String(servers[0].error).includes("401"), "safe HTTP 401 status");
  assert.ok(!(await page.locator("body").innerText()).includes(token));
  assert.ok(!JSON.stringify(await snapshot()).includes("query-private-canary"));
  await app.evidence.add("http-401-keeps-configuration", await snapshot());
  await page.getByRole("button", { name: "编辑 HTTP Fixture", exact: true }).click();
  await select("认证方式", "自定义请求头");
  await select("请求头编辑方式", "替换");
  await page.getByLabel("请求头 JSON", { exact: true }).fill(JSON.stringify({ "X-API-Key": token }));
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await connected();
  await page.getByRole("button", { name: "停用", exact: true }).click();
  await eventually(rows, (servers) => servers[0].status === "disabled", "HTTP disabled");
  await page.getByRole("button", { name: "启用", exact: true }).click(); await connected();
  await page.getByRole("button", { name: "重连", exact: true }).click(); await connected();
  await app.screenshot("mcp-http-management");
  await app.restart(); await app.settings();
  await app.page!.getByRole("button", { name: "MCP 设置", exact: true }).click();
  page = app.page!;
  await connected();
  const persisted = (await rows())[0];
  assert.deepEqual(record(persisted.selection).names, ["echo"]);
  assert.equal(record(persisted.transport).auth, "headers");
  assert.equal(persisted.bearer_configured, false);
  const configText = await readFile(resolve(workspace, "plugin-data/mcp/mcp_servers.json"), "utf8");
  assert.ok(!configText.includes(token) && !configText.includes(url));
  assert.ok(targets.every((target) => target.endsWith("?filter=read&key=query-private-canary")));
  await app.evidence.add("http-restart-retains-private-settings-and-filter", await snapshot());
  await page.getByRole("button", { name: "删除", exact: true }).click();
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await eventually(rows, (servers) => servers.length === 0, "HTTP deleted");
  assert.deepEqual(app.errors, []);
  await app.evidence.add("complete", { realHttp: true, realElectron: true, errors: app.errors });
} catch (error) {
  if (app.page) { await writeFile(resolve(output, "failure-dom.txt"), await app.page.locator("body").innerText(), "utf8"); await app.screenshot("failure"); }
  throw error;
} finally {
  await app.close();
  peer.closeAllConnections();
  await new Promise<void>((done) => peer.close(() => done()));
  const stderr = app.processErrors.join("");
  await writeFile(resolve(output, "process-stderr.log"), stderr, "utf8");
  assert.ok(!stderr.includes(token) && !stderr.includes("query-private-canary"));
  console.log(`MCP HTTP management evidence: ${output}`);
}
