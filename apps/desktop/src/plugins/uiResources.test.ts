import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { PluginUiResources } from "./uiResources";

function hash(content: string) { return createHash("sha256").update(content).digest("hex"); }

test("admission retains relative resources, stable URLs and revokes removed or untrusted packages", async () => {
  const root = await mkdtemp(join(tmpdir(), "shiori-ui-"));
  try {
    const directory = join(root, "plugins", "demo");
    await mkdir(join(directory, "ui", "dist"), { recursive: true });
    await writeFile(join(directory, "ui", "dist", "index.mjs"), "export default {}", "utf8");
    await writeFile(join(directory, "ui", "dist", "chunk.js"), "export const answer = 42", "utf8");
    await writeFile(join(directory, "ui", "dist", "lazy.mjs"), "export const version = 1", "utf8");
    await writeFile(join(directory, "secret.py"), "private", "utf8");
    const row = { id: "demo", version: "1.0.0", source: "workspace", enabled: true, state: "ACTIVE", directory, content_fingerprint: "approved", content_hashes: { "ui/dist/index.mjs": hash("export default {}"), "ui/dist/chunk.js": hash("export const answer = 42"), "ui/dist/lazy.mjs": hash("export const version = 1") }, renderer: { ui: { entry: "ui/dist/index.mjs", css: [] } } };
    const resources = new PluginUiResources(join(root, "plugins"));
    const [entry] = await resources.admit([row]);
    assert.equal((await resources.load(entry.entry)).status, 200);
    // The first request for a lazy chunk must not load a newer on-disk version.
    await writeFile(join(directory, "ui", "dist", "lazy.mjs"), "export const version = 2", "utf8");
    const changedChunk = await resources.load(new URL("lazy.mjs", entry.entry).href);
    assert.equal(changedChunk.status, 409);
    assert.match(await changedChunk.text(), /restart/);
    await writeFile(join(directory, "ui", "dist", "new.mjs"), "export const added = true", "utf8");
    assert.equal((await resources.load(new URL("new.mjs", entry.entry).href)).status, 409);
    assert.equal(await (await resources.load(new URL("chunk.js", entry.entry).href)).text(), "export const answer = 42");
    assert.deepEqual(await resources.admit([row]), [entry]);
    assert.deepEqual(await resources.admit([{ ...row, enabled: false, state: "DISABLED" }]), []);
    assert.equal((await resources.load(entry.entry)).status, 403);
    assert.deepEqual(await resources.admit([row]), [entry]);
    assert.equal((await resources.load(entry.entry)).status, 200);
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

test("a changed package version or directory requires a new application session", async () => {
  const root = await mkdtemp(join(tmpdir(), "shiori-ui-version-"));
  try {
    const directory = join(root, "demo");
    const moved = join(root, "moved");
    await mkdir(directory);
    await mkdir(moved);
    await writeFile(join(directory, "index.mjs"), "export default {}", "utf8");
    const row = { id: "demo", version: "1.0.0", source: "workspace", enabled: true, state: "ACTIVE", directory, content_fingerprint: "approved", content_hashes: { "index.mjs": hash("export default {}") }, renderer: { ui: { entry: "index.mjs", css: [] } } };
    const resources = new PluginUiResources(root);
    const [entry] = await resources.admit([row]);
    await resources.admit([{ ...row, enabled: false, state: "DISABLED" }]);
    for (const changed of [{ ...row, version: "2.0.0" }, { ...row, directory: moved }]) {
      const [rejected] = await resources.admit([changed]);
      assert.match(rejected.error ?? "", /restart the application/);
      assert.equal(rejected.entry, "");
      assert.equal((await resources.load(entry.entry)).status, 403);
    }
    assert.deepEqual(await resources.admit([row]), [entry]);
    const [restarted] = await new PluginUiResources(root).admit([{ ...row, version: "2.0.0" }]);
    assert.equal(restarted.error, undefined);
    assert.notEqual(restarted.entry, entry.entry);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("UI modified after backend activation is refused before the first main-process grant", async () => {
  const root = await mkdtemp(join(tmpdir(), "shiori-ui-approved-"));
  try {
    const directory = join(root, "demo");
    await mkdir(directory);
    const row = { id: "demo", version: "1.0.0", source: "workspace", enabled: true, state: "ACTIVE", directory, content_fingerprint: "approved-v1", content_hashes: { "index.mjs": hash("export default {version: 1}") }, renderer: { ui: { entry: "index.mjs", css: [] } } };
    await writeFile(join(directory, "index.mjs"), "export default {version: 2}", "utf8");
    const [refused] = await new PluginUiResources(root).admit([row]);
    assert.equal(refused.entry, "");
    assert.match(refused.error ?? "", /changed after approval/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("admit() grants ui, background and surface from one shared package snapshot, and refuses an untrusted plugin's declarations entirely", async () => {
  const root = await mkdtemp(join(tmpdir(), "shiori-ui-kinds-"));
  try {
    const directory = join(root, "plugins", "demo");
    await mkdir(join(directory, "ui"), { recursive: true });
    await mkdir(join(directory, "background"), { recursive: true });
    await mkdir(join(directory, "surface"), { recursive: true });
    const files = {
      "ui/index.mjs": "export default { pluginId: 'demo' }",
      "background/index.mjs": "export default { pluginId: 'demo' }",
      "surface/index.mjs": "export default { pluginId: 'demo' }",
      "style.css": ".demo {}",
    };
    for (const [path, content] of Object.entries(files)) await writeFile(join(directory, path), content, "utf8");
    const content_hashes = Object.fromEntries(Object.entries(files).map(([path, content]) => [path, hash(content)]));
    const renderer = {
      ui: { entry: "ui/index.mjs", css: ["style.css"] },
      background: { entry: "background/index.mjs", css: [] },
      surface: { entry: "surface/index.mjs", css: ["style.css"] },
    };
    const row = { id: "demo", version: "1.0.0", source: "workspace", enabled: true, state: "ACTIVE", directory, content_fingerprint: "approved", content_hashes, renderer };
    const resources = new PluginUiResources(join(root, "plugins"));

    const entries = await resources.admit([row]);
    assert.deepEqual(entries.map((entry) => entry.kind).sort(), ["background", "surface", "ui"]);
    for (const kind of ["ui", "background", "surface"]) {
      const entry = entries.find((candidate) => candidate.kind === kind);
      assert.ok(entry, `${kind} must have an entry`);
      assert.equal(entry.error, undefined, `${kind} must be granted, not refused`);
      assert.equal((await resources.load(entry.entry)).status, 200);
    }
    // The ui and surface grants share the same css asset and the same package token.
    const ui = entries.find((e) => e.kind === "ui");
    const surface = entries.find((e) => e.kind === "surface");
    assert.ok(ui && surface);
    assert.equal(ui.css[0], surface.css[0]);

    // A row that fails the top-level trust gate (untrusted state) must not
    // leak a grant for any of the three kinds, not just `ui`.
    const untrusted = await resources.admit([{ ...row, state: "UNTRUSTED" }]);
    assert.deepEqual(untrusted, []);
    for (const entry of entries) assert.equal((await resources.load(entry.entry)).status, 403);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("a package-level admission failure reports an error for every declared kind, not only the first", async () => {
  const root = await mkdtemp(join(tmpdir(), "shiori-ui-kinds-fail-"));
  try {
    const outside = join(root, "outside-plugins", "demo");
    await mkdir(outside, { recursive: true });
    await mkdir(join(root, "plugins"), { recursive: true });
    const row = {
      id: "demo", version: "1.0.0", source: "workspace", enabled: true, state: "ACTIVE",
      directory: outside, content_fingerprint: "approved", content_hashes: {},
      renderer: { background: { entry: "index.mjs", css: [] }, surface: { entry: "index.mjs", css: [] } },
    };
    const resources = new PluginUiResources(join(root, "plugins"));
    const entries = await resources.admit([row]);
    assert.deepEqual(entries.map((entry) => entry.kind).sort(), ["background", "surface"]);
    for (const entry of entries) {
      assert.equal(entry.entry, "");
      assert.match(entry.error ?? "", /escapes workspace plugins/);
    }
  } finally { await rm(root, { recursive: true, force: true }); }
});
