import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { PluginDataStore, PluginDataStoreError } from "./dataStore.js";

/** Runs one test against a throwaway user-data root, cleaned up afterwards. */
async function withRoot(run: (root: string) => Promise<void>): Promise<void> {
  const root = await mkdtemp(join(tmpdir(), "shiori-plugin-data-"));
  try {
    await run(root);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

function storeAt(
  root: string,
  options: {
    onError?: (pluginId: string, operation: "read" | "write", error: unknown) => void;
  } = {},
): PluginDataStore {
  return new PluginDataStore({ directory: join(root, "plugin-data"), ...options });
}

function dataPath(root: string, pluginId: string): string {
  return join(root, "plugin-data", `${pluginId}.json`);
}

test("a plugin's value survives a restart", async () => {
  await withRoot(async (root) => {
    await storeAt(root).write("desktop_pet", { visible: true, positions: { "a:1": { x: 2, y: 3 } } });

    // A second instance stands in for the next application launch.
    assert.deepEqual(await storeAt(root).read("desktop_pet"), {
      visible: true,
      positions: { "a:1": { x: 2, y: 3 } },
    });
  });
});

test("a plugin that has never written reads as null rather than failing", async () => {
  await withRoot(async (root) => {
    assert.equal(await storeAt(root).read("desktop_pet"), null);
  });
});

test("a corrupt file reads as null, so a plugin can fall back to its own defaults", async () => {
  await withRoot(async (root) => {
    const store = storeAt(root);
    await store.write("desktop_pet", { visible: true });
    await writeFile(dataPath(root, "desktop_pet"), "{ not json", "utf-8");

    assert.equal(await storeAt(root).read("desktop_pet"), null);
    assert.match(await readFile(dataPath(root, "desktop_pet"), "utf-8"), /not json/);
  });
});

test("a write replaces the file by rename, leaving no temporary behind", async () => {
  await withRoot(async (root) => {
    const store = storeAt(root);
    await store.write("desktop_pet", { visible: true });
    await store.write("desktop_pet", { visible: false });

    assert.deepEqual(JSON.parse(await readFile(dataPath(root, "desktop_pet"), "utf-8")), { visible: false });
    await assert.rejects(readFile(`${dataPath(root, "desktop_pet")}.tmp`, "utf-8"));
  });
});

test("concurrent writes are serialized, so the last one is what lands on disk", async () => {
  await withRoot(async (root) => {
    const store = storeAt(root);
    await Promise.all([
      store.write("desktop_pet", { order: 1 }),
      store.write("desktop_pet", { order: 2 }),
      store.write("desktop_pet", { order: 3 }),
    ]);

    assert.deepEqual(JSON.parse(await readFile(dataPath(root, "desktop_pet"), "utf-8")), { order: 3 });
  });
});

test("a stored literal null stays null", async () => {
  await withRoot(async (root) => {
    const store = storeAt(root);
    await store.write("desktop_pet", null);

    assert.equal(await store.read("desktop_pet"), null);
  });
});

test("the last known value is readable synchronously, for callers that cannot await", async () => {
  await withRoot(async (root) => {
    const store = storeAt(root);
    assert.equal(store.snapshot("desktop_pet"), null);

    await store.write("desktop_pet", { visible: true });

    assert.deepEqual(store.snapshot("desktop_pet"), { visible: true });
  });
});

test("observers see writes until they unsubscribe", async () => {
  await withRoot(async (root) => {
    const seen: Array<[string, unknown]> = [];
    const store = storeAt(root);
    const unsubscribe = store.onChanged((pluginId, value) => seen.push([pluginId, value]));

    await store.write("desktop_pet", { visible: true });
    unsubscribe();
    await store.write("desktop_pet", { visible: false });

    assert.deepEqual(seen, [["desktop_pet", { visible: true }]]);
  });
});

test("a plugin id that could escape the store directory is refused", async () => {
  await withRoot(async (root) => {
    await assert.rejects(storeAt(root).read("../../etc/passwd"), PluginDataStoreError);
    await assert.rejects(storeAt(root).write("a/b", {}), PluginDataStoreError);
  });
});

test("a read failure that is not a missing file is reported", async () => {
  await withRoot(async (root) => {
    const errors: Array<[string, string]> = [];
    const store = storeAt(root, { onError: (pluginId, operation) => errors.push([pluginId, operation]) });
    await store.write("desktop_pet", { visible: true });
    await writeFile(dataPath(root, "desktop_pet"), "{ not json", "utf-8");

    assert.equal(await store.read("desktop_pet"), null);
    assert.deepEqual(errors, [["desktop_pet", "read"]]);
  });
});
