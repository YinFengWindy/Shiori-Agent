import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { DevelopmentApp } from "./packagedDevelopmentApp";
import { Evidence, record } from "./packagedEvidence";
import { eventually } from "./packagedApp";

const repository = resolve(import.meta.dirname, "../../../..");
await mkdir(resolve(repository, ".test-tmp-root"), { recursive: true });
const output = await mkdtemp(resolve(repository, ".test-tmp-root/mcp-management-"));
const workspace = resolve(output, "workspace"), profile = resolve(output, "profile");
await mkdir(workspace); await mkdir(profile);
await writeFile(resolve(workspace, "config.toml"), '[llm]\nregistrations=[]\n[plugins.memory_optimizer]\nenabled=false\n[plugins.desktop_pet]\nenabled=false\n[plugins.mcp]\nenabled=false\n', "utf8");
const peer = resolve(output, "peer.py");
await writeFile(peer, `import json,sys,os
for line in sys.stdin:
 r=json.loads(line)
 if 'id' not in r: continue
 if r['method']=='initialize' and os.environ.get('FAIL_INIT'):
  result={'error':{'code':-32000,'message':'private-fixture-secret'}}
 else:
  result={'result':{'tools':[{'name':n,'description':n,'inputSchema':{'type':'object'}} for n in ['echo','other']]}} if r['method']=='tools/list' else {'result':{}}
 print(json.dumps({'jsonrpc':'2.0','id':r['id'],**result}),flush=True)
`, "utf8");
const executable = resolve(repository, "apps/desktop/node_modules/electron/dist", process.platform === "win32" ? "electron.exe" : "electron");
const app = new DevelopmentApp({ executable, workspace, profile }, new Evidence(output), "development");
const snapshot = async () => app.call("mcp.servers.list");
const rows = async () => { const value = await snapshot(); assert.ok(Array.isArray(value.servers)); return value.servers.map(record); };
const connected = async () => eventually(rows, (servers) => servers.length === 1 && servers[0].status === "connected", "connected stdio server");
const settings = async () => { await app.settings(); await app.page!.getByRole("button", { name: "MCP 设置", exact: true }).click(); };
try {
  await app.launch(); await app.settings();
  await app.page!.getByRole("switch", { name: "启用 MCP", exact: true }).click();
  await app.page!.getByRole("button", { name: "MCP 设置", exact: true }).click();
  const page = app.page!;
  await eventually(() => page.getByRole("button", { name: "添加服务器", exact: true }).isEnabled(), Boolean, "MCP settings ready for keyboard input");
  await page.getByRole("button", { name: "添加服务器", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("textbox", { name: "服务器 ID", exact: true }).fill("fixture");
  await page.getByRole("textbox", { name: "显示名称", exact: true }).fill("Fixture");
  await page.getByLabel("启动命令 JSON", { exact: true }).fill(JSON.stringify([resolve(repository, ".venv/Scripts/python.exe"), "-u", peer]));
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await connected();
  await app.evidence.add("create-and-discover", await snapshot());
  await page.getByRole("button", { name: "编辑 Fixture", exact: true }).click();
  await page.getByRole("combobox", { name: "工具选择模式", exact: true }).click();
  await page.getByRole("option", { name: "选择工具", exact: true }).click();
  await page.getByRole("checkbox", { name: "echo", exact: true }).check();
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await eventually(rows, (servers) => record(servers[0].selection).mode === "selected", "tool selection saved");
  await page.getByRole("button", { name: "测试连接", exact: true }).click();
  await eventually(rows, (servers) => record(servers[0].operation).kind === "test" && record(servers[0].operation).status === "succeeded", "connection probe");
  await page.getByRole("button", { name: "编辑 Fixture", exact: true }).click();
  await page.getByRole("combobox", { name: "环境变量编辑方式", exact: true }).click();
  await page.getByRole("option", { name: "替换", exact: true }).click();
  await page.getByLabel("环境变量 JSON", { exact: true }).fill(JSON.stringify({ FAIL_INIT: "1", TOKEN: "private-fixture-secret" }));
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await eventually(rows, (servers) => servers[0].status === "error", "failed connection kept");
  assert.ok(!(await page.locator("body").innerText()).includes("private-fixture-secret"));
  assert.ok(!JSON.stringify(await snapshot()).includes("private-fixture-secret"));
  await app.evidence.add("failed-config-kept-without-secrets", await snapshot());
  await page.getByRole("button", { name: "编辑 Fixture", exact: true }).click();
  await page.getByRole("combobox", { name: "环境变量编辑方式", exact: true }).click();
  await page.getByRole("option", { name: "清空", exact: true }).click();
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await connected();
  await page.getByRole("button", { name: "停用", exact: true }).click();
  await eventually(rows, (servers) => servers[0].status === "disabled", "disabled server");
  await page.getByRole("button", { name: "启用", exact: true }).click(); await connected();
  await page.getByRole("button", { name: "重连", exact: true }).click(); await connected();
  await app.screenshot("mcp-management");
  await app.restart(); await settings(); await connected();
  const persisted = (await rows())[0];
  assert.deepEqual(record(persisted.selection).names, ["echo"]);
  const configText = await readFile(resolve(workspace, "plugin-data/mcp/mcp_servers.json"), "utf8");
  assert.ok(!configText.includes(peer));
  await app.evidence.add("restart-retains-selection-and-private-launch", await snapshot());
  await app.page!.getByRole("button", { name: "删除", exact: true }).click();
  await app.page!.getByRole("button", { name: "确认删除", exact: true }).click();
  await eventually(rows, (servers) => servers.length === 0, "deleted server");
  assert.deepEqual(app.errors, []);
  await app.evidence.add("complete", { errors: app.errors, realStdio: true, realElectron: true });
} catch (error) {
  if (app.page) { await writeFile(resolve(output, "failure-dom.txt"), await app.page.locator("body").innerText(), "utf8"); await app.screenshot("failure"); }
  throw error;
} finally {
  await app.close();
  await writeFile(resolve(output, "process-stderr.log"), app.processErrors.join(""), "utf8");
  const results = record(JSON.parse(await readFile(resolve(output, "results.json"), "utf8")));
  results.nativeFileChooser = "not used by MCP management";
  results.manualAcceptance = "automated isolated Electron acceptance; no live third-party server";
  await writeFile(resolve(output, "results.json"), JSON.stringify(results, null, 2), "utf8");
  console.log(`MCP management evidence: ${output}`);
}
