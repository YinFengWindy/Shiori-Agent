import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { _electron, type ElectronApplication, type Page } from "playwright";
import { Evidence, record } from "./packagedEvidence";

/** Wait for an observable condition with a fixed deadline, never an unbounded event. */
export async function eventually<T>(read: () => Promise<T>, accepted: (value: T) => boolean, label: string) {
  const deadline = Date.now() + 30_000;
  let value: T;
  do {
    value = await read();
    if (accepted(value)) return value;
    await new Promise((done) => setTimeout(done, 100));
  } while (Date.now() < deadline);
  throw new Error(`Timed out: ${label}; last=${JSON.stringify(value)}`);
}

/** Drive the unmodified packaged entry; only the native chooser's selected file is substituted. */
export class PackagedApp {
  app: ElectronApplication | undefined;
  page: Page | undefined;
  readonly errors: string[] = [];
  constructor(readonly paths: { executable: string; workspace: string; profile: string }, readonly evidence: Evidence, readonly version: string) {}

  async launch() {
    const env: Record<string, string> = {};
    for (const [key, value] of Object.entries(process.env)) if (value !== undefined) env[key] = value;
    env.SHIORI_DESKTOP_WORKSPACE = this.paths.workspace;
    env.SHIORI_DESKTOP_USER_DATA_DIR = this.paths.profile;
    delete env.SHIORI_RENDERER_DEV_SERVER_URL;
    delete env.ELECTRON_RUN_AS_NODE;
    this.app = await _electron.launch({ executablePath: this.paths.executable, env, timeout: 45_000 });
    const identity = await this.app.evaluate(({ app }) => ({ packaged: app.isPackaged, version: app.getVersion(), appPath: app.getAppPath(), resources: process.resourcesPath, workspace: process.env.SHIORI_DESKTOP_WORKSPACE, profile: app.getPath("userData"), electron: process.versions.electron }));
    assert.equal(identity.packaged, true);
    assert.equal(identity.version, this.version);
    assert.equal(identity.workspace, this.paths.workspace);
    assert.equal(identity.profile, this.paths.profile);
    assert.equal(identity.appPath, resolve(this.paths.executable, "../resources/app.asar"));
    this.page = await eventually(async () => this.app!.windows().find((candidate) => candidate.url().endsWith("/index.html")), (page) => Boolean(page), "main packaged window");
    assert.ok(this.page);
    this.page.setDefaultTimeout(30_000);
    this.page.on("pageerror", (error) => this.errors.push(error.message));
    await Promise.race([this.page.locator(".app-frame").waitFor(), this.page.getByRole("button", { name: "暂时跳过", exact: true }).waitFor()]);
    if (await this.page.getByRole("button", { name: "暂时跳过", exact: true }).isVisible()) await this.page.getByRole("button", { name: "暂时跳过", exact: true }).click();
    await this.page.locator(".app-frame").waitFor();
    await this.evidence.add("packaged-launch", identity);
  }

  async close() { await this.app?.close(); this.app = undefined; this.page = undefined; }
  async restart() { await this.close(); await this.launch(); }
  async settings() {
    await this.page!.getByRole("button", { name: "设置", exact: true }).click();
    await this.page!.getByRole("button", { name: "插件", exact: true }).click();
  }
  async screenshot(name: string, page = this.page!) {
    const window = await this.app!.browserWindow(page);
    const png = await window.evaluate(async (window) => (await window.capturePage()).toPNG().toString("base64"));
    assert.ok(png, "packaged window capture was empty");
    await writeFile(resolve(this.evidence.output, `${name}.png`), Buffer.from(png, "base64"));
  }
  async bridge(method: string, payload: Record<string, unknown> = {}) {
    return this.page!.evaluate(({ method, payload }) => window.miraDesktop.invoke({ method, payload }), { method, payload });
  }
  async call(method: string, payload: Record<string, unknown> = {}) {
    const response = await this.bridge(method, payload);
    assert.equal(response.error, null, `${method}: ${JSON.stringify(response.error)}`);
    return response.payload;
  }
  async roster() {
    const result = await this.call("plugins.list");
    assert.ok(Array.isArray(result.plugins));
    return result.plugins.map(record).filter((item) => item.id === "external_demo");
  }
  async state(expected: string) {
    return eventually(() => this.roster(), (rows) => rows.length > 0 && rows.every((row) => row.state === expected && (expected !== "ACTIVE" || (Array.isArray(row.pending_renderer_kinds) && !row.pending_renderer_kinds.length))), `fixture ${expected}`);
  }
  async choose(archive: string, update = false) {
    assert.ok(this.app);
    await this.app.evaluate(({ dialog }, path) => { dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [path] }); }, archive);
    if (update) await this.page!.getByRole("radio", { name: "选择 external_demo", exact: true }).check();
    await this.page!.getByRole("button", { name: update ? "更新插件" : "安装插件 ZIP", exact: true }).click();
  }
  async install(archive: string, { update = false, confirm = true } = {}) {
    await this.choose(archive, update);
    const dialog = this.page!.getByRole("dialog", { name: update ? "更新插件" : "安装插件", exact: true });
    await dialog.waitFor();
    await dialog.getByRole("button", { name: confirm ? (update ? "信任并更新" : "信任并安装") : "取消", exact: true }).click();
    await dialog.waitFor({ state: "hidden" });
    if (confirm) await eventually(() => this.roster(), (rows) => rows.some((row) => row.pending_operation === (update ? "update" : "install")), "queued package");
  }
}
