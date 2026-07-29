import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { WorldAssetManager, WorldAssetTimeoutError } from "./worldAssetManager";

type FakeAsset = { id: string };

describe("WorldAssetManager", () => {
  it("deduplicates preload, reference counts current assets, and evicts unused LRU entries", async () => {
    const loads: string[] = [];
    const destroyed: string[] = [];
    const manager = new WorldAssetManager<FakeAsset>({
      softBudgetBytes: 12,
      maxEntries: 2,
      loader: async (entry) => {
        loads.push(entry.id);
        return { asset: { id: entry.id }, sizeBytes: 8 };
      },
      destroy: (asset) => destroyed.push(asset.id),
    });
    manager.registerManifest([
      { id: "bg-1", url: "shiori-asset://local/bg-1", kind: "background" },
      { id: "bg-2", url: "shiori-asset://local/bg-2", kind: "background" },
    ]);

    const [first, duplicate] = await Promise.all([
      manager.acquire("bg-1"),
      manager.acquire("bg-1"),
    ]);
    assert.equal(first, duplicate);
    assert.deepEqual(loads, ["bg-1"]);
    manager.release("bg-1");
    await manager.preload(["bg-2"]);
    assert.deepEqual(destroyed, ["bg-2"]);
    assert.equal(manager.stats().retainedEntries, 1);

    manager.release("bg-1");
    assert.deepEqual(destroyed, ["bg-2"]);
    manager.dispose();
    assert.deepEqual(destroyed, ["bg-2", "bg-1"]);
    assert.equal(manager.stats().manifestEntries, 0);
  });

  it("rejects URLs that bypass the controlled local asset transport", () => {
    const manager = new WorldAssetManager<FakeAsset>({
      loader: async (entry) => ({ asset: { id: entry.id } }),
      destroy: () => undefined,
    });
    assert.throws(() => manager.registerManifest([
      { id: "private", url: "file:///C:/private.png", kind: "cg" },
    ]), /controlled local asset transport/);
  });

  it("replaces an unused manifest URL before the asset is loaded again", async () => {
    const urls: string[] = [];
    const manager = new WorldAssetManager<FakeAsset>({
      softBudgetBytes: 0,
      loader: async (entry) => {
        urls.push(entry.url);
        return { asset: { id: entry.id }, sizeBytes: 1 };
      },
      destroy: () => undefined,
    });
    manager.registerManifest([{ id: "bg", url: "shiori-asset://local/old", kind: "background" }]);
    await manager.preload(["bg"]);
    manager.registerManifest([{ id: "bg", url: "shiori-asset://local/new", kind: "background" }]);
    await manager.preload(["bg"]);
    assert.deepEqual(urls, ["shiori-asset://local/old", "shiori-asset://local/new"]);
    manager.dispose();
  });

  it("supports caller cancellation without cancelling a shared load", async () => {
    let finish: ((value: { asset: FakeAsset; sizeBytes: number }) => void) | undefined;
    const manager = new WorldAssetManager<FakeAsset>({
      loader: async () => await new Promise((resolve) => { finish = resolve; }),
      destroy: () => undefined,
    });
    manager.registerManifest([{ id: "cg", url: "shiori-asset://local/cg", kind: "cg" }]);
    const controller = new AbortController();
    const cancelled = manager.preload(["cg"], { signal: controller.signal });
    const shared = manager.preload(["cg"]);
    controller.abort(new Error("cancelled by scene change"));
    await assert.rejects(cancelled, /scene change/);
    finish?.({ asset: { id: "cg" }, sizeBytes: 4 });
    assert.equal((await shared).get("cg")?.id, "cg");
    manager.dispose();
  });

  it("aborts stalled loaders at the configured timeout", async () => {
    const manager = new WorldAssetManager<FakeAsset>({
      timeoutMs: 5,
      loader: async (_entry, { signal }) => await new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () => reject(new Error("loader aborted")), { once: true });
      }),
      destroy: () => undefined,
    });
    manager.registerManifest([{ id: "slow", url: "shiori-asset://local/slow", kind: "cg" }]);
    await assert.rejects(manager.preload(["slow"]), WorldAssetTimeoutError);
    assert.equal(manager.stats().pendingEntries, 0);
    manager.dispose();
  });

  it("cancels pending loads when disposed and remains idempotent", async () => {
    let aborted = false;
    const manager = new WorldAssetManager<FakeAsset>({
      loader: async (_entry, { signal }) => await new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () => {
          aborted = true;
          reject(new Error("disposed"));
        }, { once: true });
      }),
      destroy: () => undefined,
    });
    manager.registerManifest([{ id: "pending", url: "shiori-asset://local/pending", kind: "cg" }]);
    const pending = manager.preload(["pending"]);
    manager.dispose();
    manager.dispose();
    await assert.rejects(pending, /disposed/);
    assert.equal(aborted, true);
    assert.deepEqual(manager.stats(), {
      manifestEntries: 0,
      readyEntries: 0,
      pendingEntries: 0,
      retainedEntries: 0,
      totalBytes: 0,
    });
  });
});
