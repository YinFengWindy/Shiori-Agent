import assert from "node:assert/strict";
import { access } from "node:fs/promises";
import { resolve } from "node:path";
import { _electron } from "playwright";
import { PackagedApp, eventually } from "./packagedApp";

/** Runs the production desktop entries against a separate development workspace and profile. */
export class DevelopmentApp extends PackagedApp {
  async launch() {
    const repository = resolve(import.meta.dirname, "../../../..");
    const env: Record<string, string> = { SHIORI_DESKTOP_WORKSPACE: this.paths.workspace, SHIORI_DESKTOP_USER_DATA_DIR: this.paths.profile };
    for (const [key, value] of Object.entries(process.env)) if (value !== undefined && !(key in env)) env[key] = value;
    delete env.SHIORI_RENDERER_DEV_SERVER_URL;
    delete env.ELECTRON_RUN_AS_NODE;
    await access(this.paths.executable);
    this.app = await _electron.launch({ executablePath: this.paths.executable, args: [resolve(repository, "apps/desktop")], env, timeout: 45_000 });
    this.app.process().stderr?.on("data", (chunk: Buffer) => this.processErrors.push(chunk.toString("utf8")));
    const identity = await this.app.evaluate(({ app }) => ({ packaged: app.isPackaged, appPath: app.getAppPath(), profile: app.getPath("userData"), workspace: process.env.SHIORI_DESKTOP_WORKSPACE }));
    assert.equal(identity.packaged, false);
    assert.equal(identity.appPath, resolve(repository, "apps/desktop"));
    assert.equal(identity.profile, this.paths.profile);
    assert.equal(identity.workspace, this.paths.workspace);
    this.page = await eventually(async () => this.app!.windows().find((page) => page.url().endsWith("/index.html")), Boolean, "production development window");
    assert.ok(this.page);
    this.page.setDefaultTimeout(30_000);
    this.page.on("pageerror", (error) => this.errors.push(error.message));
    await Promise.race([this.page.locator(".app-frame").waitFor(), this.page.getByRole("button", { name: "跳过", exact: true }).waitFor()]);
    if (await this.page.getByRole("button", { name: "跳过", exact: true }).isVisible()) await this.page.getByRole("button", { name: "跳过", exact: true }).click();
    await this.page.locator(".app-frame").waitFor();
    await this.evidence.add("development-production-entry", identity);
  }
}
