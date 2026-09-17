import { app, BrowserWindow, ipcMain, protocol, session } from "electron";
import { resolve } from "node:path";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { PluginUiResources } from "../../dist/plugins/uiResources.js";
import { registerDesktopContentSecurityPolicy } from "../../dist/windowSecurity.js";

protocol.registerSchemesAsPrivileged([{ scheme: "shiori-plugin", privileges: { standard: true, secure: true, corsEnabled: true, supportFetchAPI: true } }]);
await app.whenReady();
const resources = new PluginUiResources(resolve(process.env.SHIORI_PLUGIN_UI_QA_ROOT, "plugins"));
const approved = Object.fromEntries(await Promise.all(["demo", "broken"].map(async (id) => [id, Object.fromEntries(await Promise.all(["index.mjs", "chunk.mjs", "lazy.mjs", "style.css"].map(async (name) => [`ui/dist/${name}`, createHash("sha256").update(await readFile(resolve(process.env.SHIORI_PLUGIN_UI_QA_ROOT, "plugins", id, "ui", "dist", name))).digest("hex")])))])));
globalThis.pluginUiQaEnabled = true;
ipcMain.handle("desktop:invoke", async (_event, request) => {
  const rows = ["demo", "broken"].map((id) => ({
    id, name: id, candidate_id: id, source: "workspace", directory: resolve(process.env.SHIORI_PLUGIN_UI_QA_ROOT, "plugins", id),
    enabled: globalThis.pluginUiQaEnabled, can_toggle: true, state: globalThis.pluginUiQaEnabled ? "ACTIVE" : "DISABLED", error: "", diagnostic: null,
    content_fingerprint: `fixture-${id}`, content_hashes: approved[id],
    renderer: { ui: { entry: "ui/dist/index.mjs", css: ["ui/dist/style.css"] } },
  }));
  const entries = await resources.admit(rows);
  const plugins = rows.map((row) => ({ ...row, renderer_ui: entries.find((entry) => entry.pluginId === row.id && entry.kind === "ui") }));
  return { assets: [], value: { id: "qa", type: "response", method: request.method, payload: { plugins }, error: null } };
});
ipcMain.on("desktop:renderer-diagnostic", () => undefined);
registerDesktopContentSecurityPolicy(session.defaultSession.webRequest, undefined);
protocol.handle("shiori-plugin", (request) => resources.load(request.url));
const window = new BrowserWindow({ show: false, webPreferences: { preload: resolve("apps/desktop/dist/preload.js"), contextIsolation: true, nodeIntegration: false, sandbox: false } });
await window.loadFile(resolve(process.env.SHIORI_PLUGIN_UI_QA_ROOT, "renderer", "index.html"));
