import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { PluginUiResources } from "./uiResources";

test("admission retains relative resources, stable URLs and revokes removed or untrusted packages", async () => {
  const root = await mkdtemp(join(tmpdir(), "shiori-ui-"));
  try {
    const directory = join(root, "plugins", "demo");
    await mkdir(join(directory, "ui", "dist"), { recursive: true });
    await writeFile(join(directory, "ui", "dist", "index.mjs"), "export default {}", "utf8");
    await writeFile(join(directory, "ui", "dist", "chunk.js"), "export const answer = 42", "utf8");
    await writeFile(join(directory, "secret.py"), "private", "utf8");
    const row = { id: "demo", source: "workspace", enabled: true, state: "ACTIVE", directory, renderer: { ui: { entry: "ui/dist/index.mjs", css: [] } } };
    const resources = new PluginUiResources(join(root, "plugins"));
    const [entry] = await resources.admit([row]);
    assert.equal((await resources.load(entry.entry)).status, 200);
    assert.equal(await (await resources.load(new URL("chunk.js", entry.entry).href)).text(), "export const answer = 42");
    assert.deepEqual(await resources.admit([row]), [entry]);
    assert.equal((await resources.load(new URL("../../secret.py", entry.entry).href)).status, 403);
    assert.equal((await resources.load(entry.entry.replace("index.mjs", "%2e%2e%2fsecret.py"))).status, 403);
    const outside = join(root, "outside");
    await mkdir(outside);
    await writeFile(join(outside, "escape.mjs"), "private", "utf8");
    await symlink(outside, join(directory, "ui", "dist", "linked"), "junction");
    assert.equal((await resources.load(new URL("linked/escape.mjs", entry.entry).href)).status, 403);
    assert.deepEqual(await resources.admit([{ ...row, state: "UNTRUSTED" }]), []);
    assert.equal((await resources.load(entry.entry)).status, 403);
    assert.deepEqual(await resources.admit([row, row]), []);
    await resources.admit([row]);
    assert.deepEqual(await resources.admit([]), []);
  } finally { await rm(root, { recursive: true, force: true }); }
});
