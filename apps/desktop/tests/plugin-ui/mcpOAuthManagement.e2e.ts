import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { resolve } from "node:path";
import { DevelopmentApp } from "./packagedDevelopmentApp";
import { Evidence, record } from "./packagedEvidence";
import { eventually } from "./packagedApp";

const repository = resolve(import.meta.dirname, "../../../..");
await mkdir(resolve(repository, ".test-tmp-root"), { recursive: true });
const output = await mkdtemp(resolve(repository, ".test-tmp-root/mcp-oauth-management-"));
const workspace = resolve(output, "workspace"), profile = resolve(output, "profile");
await mkdir(workspace); await mkdir(profile);
await writeFile(resolve(workspace, "config.toml"), '[llm]\nregistrations=[]\n[plugins.memory_optimizer]\nenabled=false\n[plugins.desktop_pet]\nenabled=false\n[plugins.mcp]\nenabled=false\n', "utf8");
let origin = "", challenge = "", refreshes = 0;
const token = "oauth-access-canary";
const peer = createServer((request, response) => {
  void (async () => {
    const url = new URL(request.url ?? "/", origin);
    response.setHeader("content-type", "application/json");
    let body = ""; for await (const chunk of request) body += String(chunk);
    const send = (value: unknown) => response.end(JSON.stringify(value));
    if (url.pathname.startsWith("/.well-known/oauth-protected-resource")) { send({ resource: `${origin}/mcp`, authorization_servers: [origin] }); return; }
    if (url.pathname.startsWith("/.well-known/")) { send({ issuer: origin, authorization_endpoint: `${origin}/authorize`, token_endpoint: `${origin}/token`, registration_endpoint: `${origin}/register`, response_types_supported: ["code"], code_challenge_methods_supported: ["S256"], token_endpoint_auth_methods_supported: ["none"], authorization_response_iss_parameter_supported: true }); return; }
    if (url.pathname === "/register") { send({ ...record(JSON.parse(body)), client_id: "fixture-client" }); return; }
    if (url.pathname === "/authorize") {
      challenge = url.searchParams.get("code_challenge") ?? "";
      const callback = new URL(url.searchParams.get("redirect_uri")!);
      callback.searchParams.set("code", "oauth-code-canary"); callback.searchParams.set("state", url.searchParams.get("state")!); callback.searchParams.set("iss", origin);
      response.writeHead(302, { location: callback.href }); response.end(); return;
    }
    if (url.pathname === "/token") {
      const form = new URLSearchParams(body);
      if (form.get("grant_type") === "refresh_token") refreshes += 1;
      else assert.equal(createHash("sha256").update(form.get("code_verifier")!).digest("base64url"), challenge);
      send({ access_token: token, token_type: "Bearer", refresh_token: "oauth-refresh-canary", expires_in: 3600 }); return;
    }
    if (request.headers.authorization !== `Bearer ${token}`) { response.writeHead(401, { "www-authenticate": `Bearer resource_metadata="${origin}/.well-known/oauth-protected-resource"` }); send({ error: "unauthorized" }); return; }
    if (request.method !== "POST") { response.writeHead(request.method === "DELETE" ? 200 : 405); response.end(); return; }
    const rpc = record(JSON.parse(body));
    if (!("id" in rpc)) { response.writeHead(202); response.end(); return; }
    const result = rpc.method === "server/discover" ? { error: { code: -32601, message: "Unknown method" } }
      : rpc.method === "initialize" ? { result: { protocolVersion: "2025-11-25", capabilities: { tools: {} }, serverInfo: { name: "fixture", version: "1" } } }
      : { result: { tools: [{ name: "echo", inputSchema: { type: "object" } }] } };
    response.setHeader("mcp-session-id", "fixture"); send({ jsonrpc: "2.0", id: rpc.id, ...result });
  })().catch(() => { response.writeHead(500); response.end(); });
});
await new Promise<void>((ready) => peer.listen(0, "127.0.0.1", ready));
const address = peer.address(); assert.ok(address && typeof address !== "string"); origin = `http://127.0.0.1:${address.port}`;
const executable = resolve(repository, "apps/desktop/node_modules/electron/dist", process.platform === "win32" ? "electron.exe" : "electron");
const app = new DevelopmentApp({ executable, workspace, profile }, new Evidence(output), "development");
const rows = async () => { const value = await app.call("mcp.servers.list"); assert.ok(Array.isArray(value.servers)); return value.servers.map(record); };
const connected = async () => eventually(rows, (servers) => servers.length === 1 && servers[0].status === "connected", "OAuth connected");
const browser = async (hold: boolean) => app.app!.evaluate(({ shell }, hold) => {
  process.env.MCP_FIXTURE_OPEN_COUNT = "0";
  shell.openExternal = async (url) => {
    process.env.MCP_FIXTURE_OPEN_COUNT = String(Number(process.env.MCP_FIXTURE_OPEN_COUNT) + 1);
    if (!hold) { const authorization = await fetch(url, { redirect: "manual" }); await fetch(authorization.headers.get("location")!); }
  };
}, hold);
const opens = async () => app.app!.evaluate(() => Number(process.env.MCP_FIXTURE_OPEN_COUNT));
const select = async (name: string, option: string) => { await app.page!.getByRole("combobox", { name, exact: true }).click(); await app.page!.getByRole("option", { name: option, exact: true }).click(); };
try {
  await app.launch(); await browser(true); await app.settings();
  await app.page!.getByRole("switch", { name: "启用 MCP", exact: true }).click();
  await app.page!.getByRole("button", { name: "MCP 设置", exact: true }).click();
  let page = app.page!;
  await eventually(() => page.getByRole("button", { name: "添加服务器", exact: true }).isEnabled(), Boolean, "management ready");
  await page.getByRole("button", { name: "添加服务器", exact: true }).click();
  await page.getByRole("textbox", { name: "服务器 ID", exact: true }).fill("oauth_fixture");
  await select("连接方式", "Streamable HTTP"); await page.getByLabel("服务器地址", { exact: true }).fill(`${origin}/mcp`);
  await select("认证方式", "OAuth"); await page.getByRole("button", { name: "保存", exact: true }).click();
  await eventually(rows, (servers) => servers.length === 1 && record(servers[0].oauth).status === "login_required", "login required");
  assert.equal(await opens(), 0);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await eventually(opens, (count) => count === 1, "explicit browser launch");
  await app.screenshot("mcp-oauth-waiting");
  await page.getByRole("button", { name: "取消操作", exact: true }).click();
  await eventually(rows, (servers) => record(servers[0].oauth).status === "login_required" && record(servers[0].operation).status !== "running", "cancelled login");
  await browser(false); await page.getByRole("button", { name: "登录", exact: true }).click(); await connected();
  assert.equal(await opens(), 1);
  await app.screenshot("mcp-oauth-authorized");
  await page.getByRole("button", { name: "刷新授权", exact: true }).click();
  await eventually(rows, (servers) => record(servers[0].operation).kind === "refresh" && record(servers[0].operation).status === "succeeded", "refresh completed");
  assert.equal(refreshes, 1); assert.equal(await opens(), 1);
  await app.restart(); await browser(false); await app.settings();
  await app.page!.getByRole("button", { name: "MCP 设置", exact: true }).click(); page = app.page!;
  await connected(); assert.equal(await opens(), 0);
  await app.evidence.add("restart-preserves-login-without-browser", await app.call("mcp.servers.list"));
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  await eventually(rows, (servers) => record(servers[0].oauth).status === "login_required" && servers[0].status === "disconnected", "logged out");
  await app.screenshot("mcp-oauth-logged-out");
  const projection = JSON.stringify(await app.call("mcp.servers.list")) + await page.locator("body").innerText();
  for (const secret of [token, "oauth-code-canary", "oauth-refresh-canary"]) assert.ok(!projection.includes(secret));
  assert.deepEqual(app.errors, []);
  await app.evidence.add("complete", { realElectron: true, realOAuthHttp: true, browser: "shell.openExternal substituted with a fixture HTTP browser", errors: app.errors });
} catch (error) {
  if (app.page) { await writeFile(resolve(output, "failure-dom.txt"), await app.page.locator("body").innerText(), "utf8"); await app.screenshot("failure"); }
  throw error;
} finally {
  await app.close(); peer.closeAllConnections(); await new Promise<void>((done) => peer.close(() => done()));
  const stderr = app.processErrors.join(""); await writeFile(resolve(output, "process-stderr.log"), stderr, "utf8");
  for (const secret of [token, "oauth-code-canary", "oauth-refresh-canary"]) assert.ok(!stderr.includes(secret));
  console.log(`MCP OAuth management evidence: ${output}`);
}
