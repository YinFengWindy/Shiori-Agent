import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { PackagedApp, eventually } from "./packagedApp";
import { pendingPackage, record } from "./packagedEvidence";

/** Persisted backend fixture observations, independent of its RPC availability. */
export async function backendState(app: PackagedApp) {
  return record(JSON.parse(await readFile(resolve(app.paths.workspace, "plugin-data/external_demo/kv.json"), "utf8")));
}

/** Enable through the actual management control after a restart-only install. */
export async function activate(app: PackagedApp) {
  await app.settings();
  const rows = await app.roster();
  if (rows[0]?.state === "DISABLED") await app.page!.getByRole("switch", { name: "启用 external_demo", exact: true }).click();
  await app.state("ACTIVE");
}

/** Exercise all four entry points and their actual cross-renderer communication. */
export async function exercise(app: PackagedApp, version: string) {
  await app.page!.getByRole("button", { name: "External lifecycle", exact: true }).click();
  await app.page!.getByRole("heading", { name: `External fixture ${version}`, exact: true }).waitFor();
  await app.page!.getByRole("button", { name: "Inspect all entries", exact: true }).click();
  await app.page!.getByTestId("fixture-result").filter({ hasText: "background" }).waitFor();
  const result = record(JSON.parse(await app.page!.getByTestId("fixture-result").innerText()));
  assert.equal(record(result.backend).version, version);
  assert.equal(record(result.backend).tool, `external tool ${version}`);
  assert.equal(record(result.background).version, version);
  assert.equal(record(result.background).alive, true);
  assert.match(String(record(result.background).reactVersion), /^19\./);
  assert.ok(await app.page!.locator('link[rel="stylesheet"][href^="shiori-plugin:"]').count(), "fixture stylesheet was not installed");
  const backgroundFile = resolve(app.paths.profile, "plugin-data/external_demo.json");
  const background = record(JSON.parse(await readFile(backgroundFile, "utf8")));
  await eventually(async () => record(JSON.parse(await readFile(backgroundFile, "utf8"))), (state) => Number(state.ticks) > Number(background.ticks), "background timer persisted progress");
  await app.page!.getByRole("button", { name: "Send plugin event", exact: true }).click();
  await app.page!.getByTestId("fixture-events").filter({ hasText: "UI events 1" }).waitFor();
  await eventually(async () => record(JSON.parse(await readFile(backgroundFile, "utf8"))), (state) => Number(state.events) >= 1, "background event subscription");
  const surface = await eventually(async () => app.app!.windows().find((page) => page.url().includes("/surface.html")), Boolean, "fixture surface");
  assert.ok(surface);
  await surface.getByRole("heading", { name: `External surface ${version}`, exact: true }).waitFor();
  await surface.getByRole("button", { name: "Surface RPC", exact: true }).click();
  await surface.getByText(`external tool ${version}`, { exact: true }).waitFor();
  await app.screenshot(`surface-${version}`, surface);
  const observed = Number((await backendState(app)).role_events ?? 0);
  await app.call("roles.create", { role_id: "qa-observed", name: "QA observed", system_prompt: "fixture" });
  await app.call("roles.delete", { role_id: "qa-observed" });
  await eventually(() => backendState(app), (state) => state.role_events === observed + 1, "active backend event subscription");
  await app.evidence.add(`four-entries-${version}`, result);
}

/** Prove teardown by absence, persisted tool audit, timer quiescence and a real host event. */
export async function assertNoResidue(app: PackagedApp, backgroundStarted = true) {
  const response = await app.bridge("plugin.external_demo.inspect");
  assert.ok(response.error, "disabled RPC remained callable");
  await eventually(async () => app.page!.getByRole("button", { name: "External lifecycle", exact: true }).count(), (count) => count === 0, "UI removed");
  await eventually(async () => app.app!.windows().filter((page) => page.url().includes("/surface.html")).length, (count) => count === 0, "surface destroyed");
  await eventually(() => backendState(app), (state) => record(state.backend_teardown).tool_absent === true, "tool unregistered before teardown audit");
  const profileState = resolve(app.paths.profile, "plugin-data/external_demo.json");
  assert.ok(!backgroundStarted || existsSync(profileState), "observed background state disappeared");
  if (backgroundStarted) {
    await eventually(async () => record(JSON.parse(await readFile(profileState, "utf8"))), (state) => state.alive === false, "background timer disposed");
    const before = await readFile(profileState, "utf8");
    await new Promise((done) => setTimeout(done, 400));
    assert.equal(await readFile(profileState, "utf8"), before, "background kept writing after teardown");
  }
  await eventually(async () => (await Promise.all(app.app!.windows().map((page) => page.locator('link[rel="stylesheet"][href^="shiori-plugin:"]').count()))).reduce((total, count) => total + count, 0), (count) => count === 0, "plugin styles removed from every renderer");
  const before = await backendState(app);
  await app.call("roles.create", { role_id: "qa-disposable", name: "QA disposable", system_prompt: "fixture" });
  await app.call("roles.delete", { role_id: "qa-disposable" });
  assert.equal((await backendState(app)).role_events, before.role_events, "disabled event subscriber was invoked");
  await app.evidence.add("no-residual-tool-rpc-event-background-ui-surface", { rpcError: response.error, backend: await backendState(app) });
}

/** Installation, hot toggle, update rollback, removal and explicit retained-data reauthorization. */
export async function lifecycle(app: PackagedApp, fixture: string) {
  const archive = (version: string) => resolve(fixture, `external_demo-${version}-valid.zip`);
  await app.settings();
  await app.install(archive("1.0.0"), { confirm: false });
  assert.equal(existsSync(resolve(app.paths.workspace, "plugin-data/external_demo/kv.json")), false);
  assert.equal((await app.roster()).length, 0);
  await app.evidence.add("cancel-install-does-not-execute");
  await app.install(archive("1.0.0"));
  await app.screenshot("01-install-pending");
  assert.ok((await app.bridge("plugin.external_demo.inspect")).error);
  await app.restart();
  await activate(app);
  await exercise(app, "1.0.0");
  await app.page!.getByRole("button", { name: "Save retained data", exact: true }).click();
  await eventually(() => backendState(app), (state) => state.saved === "retained-user-value", "saved plugin data");
  await app.settings();
  await app.page!.getByRole("switch", { name: "启用 external_demo", exact: true }).click();
  await app.state("DISABLED");
  await assertNoResidue(app);
  await app.screenshot("02-disabled");
  await app.page!.getByRole("switch", { name: "启用 external_demo", exact: true }).click();
  await app.state("ACTIVE");
  await exercise(app, "1.0.0");
  await app.settings();
  await app.install(archive("2.0.0"), { update: true });
  assert.equal((await app.call("plugin.external_demo.inspect")).version, "1.0.0");
  const journal = await pendingPackage(app.paths.workspace);
  await app.evidence.add("update-staged-old-version-still-active", journal.journal);
  await app.screenshot("03-update-pending");
  await app.restart();
  await activate(app);
  await exercise(app, "2.0.0");
  await app.settings();
  await app.install(archive("3.0.0"), { update: true });
  const broken = await pendingPackage(app.paths.workspace);
  await writeFile(resolve(broken.root, "package/backend/plugin.py"), "tampered after explicit confirmation", "utf8");
  await app.restart();
  await activate(app);
  const [row] = await app.roster();
  assert.ok(row.package_operation_error);
  assert.equal((await app.call("plugin.external_demo.inspect")).version, "2.0.0");
  assert.equal((await backendState(app)).saved, "retained-user-value");
  await app.screenshot("04-failed-update-retains-old");
  await app.evidence.add("corrupt-confirmed-update-rolls-back", row);
  await app.page!.getByRole("radio", { name: "选择 external_demo", exact: true }).check();
  await app.page!.getByRole("button", { name: "卸载插件", exact: true }).click();
  const dialog = app.page!.getByRole("dialog", { name: "卸载插件", exact: true });
  assert.equal(await dialog.getByRole("checkbox").isChecked(), false);
  await dialog.getByRole("button", { name: "卸载", exact: true }).click();
  await dialog.waitFor({ state: "hidden" });
  await app.restart();
  await app.settings();
  assert.equal((await app.roster()).length, 0);
  const retained = await readFile(resolve(app.paths.workspace, "plugin-data/external_demo/kv.json"), "utf8");
  await app.install(archive("2.0.0"), { confirm: false });
  assert.equal(await readFile(resolve(app.paths.workspace, "plugin-data/external_demo/kv.json"), "utf8"), retained);
  assert.ok((await app.bridge("plugin.external_demo.inspect")).error);
  await app.evidence.add("uninstall-retains-data-cancelled-reinstall-cannot-read-it");
  await app.install(archive("2.0.0"));
  assert.equal(await readFile(resolve(app.paths.workspace, "plugin-data/external_demo/kv.json"), "utf8"), retained);
  await app.restart();
  await activate(app);
  assert.equal((await app.call("plugin.external_demo.inspect")).saved, "retained-user-value");
  await app.evidence.add("explicit-reinstall-confirmation-restores-data-access");
}
