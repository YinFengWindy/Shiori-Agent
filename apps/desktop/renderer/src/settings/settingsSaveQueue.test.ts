import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { setImmediate } from "node:timers/promises";
import type { SaveSettingsResult, SettingsFormData, SettingsSaveOptions } from "../../../src/bridge/shared.js";
import { SettingsSaveQueue } from "./settingsSaveQueue.js";
import { createSettingsDraft } from "./testFixtures.js";

function editedDraft(marker: string) {
  const draft = createSettingsDraft();
  draft.memory.engine = marker;
  return draft;
}

describe("SettingsSaveQueue", () => {
  it("retries a lost response with the same operation and pauses later edits until recovery", async () => {
    const calls: { draft: SettingsFormData; options?: SettingsSaveOptions }[] = [];
    let persisted = createSettingsDraft();
    let generation = 4;
    const queue = new SettingsSaveQueue({
      api: {
        saveSettings: async (draft, options) => {
          calls.push({ draft, options });
          if (calls.length === 1) throw new Error("response lost");
          persisted = draft;
          return { ok: true, generation: ++generation };
        },
        readSettings: async () => ({ configPath: "config.toml", formData: persisted, generation }),
      },
      onApplied: () => undefined,
      onStatus: () => undefined,
    });
    queue.reset(4);
    queue.enqueue(editedDraft("first"));
    await setImmediate();
    queue.enqueue(editedDraft("second"));
    await setImmediate();
    assert.equal(calls.length, 1);
    queue.retry();
    await setImmediate();
    assert.equal(calls.length, 3);
    assert.deepEqual(calls[1], calls[0]);
    assert.equal(calls[2]?.draft.memory.engine, "second");
    assert.equal(calls[2]?.options?.expectedGeneration, 5);
    assert.notEqual(calls[2]?.options?.operationId, calls[0]?.options?.operationId);
  });

  it("keeps generation conflicts paused despite later edits and explicit retry", async () => {
    const versions: (number | undefined)[] = [];
    const queue = new SettingsSaveQueue({
      api: {
        saveSettings: async (_draft, options) => {
          versions.push(options?.expectedGeneration);
          return { ok: false, error: { code: "runtime_generation_conflict", message: "changed externally" } };
        },
        readSettings: async () => { throw new Error("must not refresh conflict version"); },
      },
      onApplied: () => assert.fail("conflict cannot apply"),
      onStatus: () => undefined,
    });
    queue.reset(1);
    queue.enqueue(editedDraft("first"));
    await setImmediate();
    queue.enqueue(editedDraft("second"));
    queue.retry();
    await setImmediate();
    assert.deepEqual(versions, [1, 1]);
  });

  it("saves corrected drafts after a definite validation rejection", async () => {
    const calls: string[] = [];
    const queue = new SettingsSaveQueue({
      api: {
        saveSettings: async (draft) => {
          calls.push(draft.memory.engine);
          return calls.length === 1
            ? { ok: false, error: { code: "runtime_config_invalid", message: "invalid" } }
            : { ok: true, generation: 2 };
        },
        readSettings: async () => ({ configPath: "config.toml", formData: editedDraft("corrected"), generation: 2 }),
      },
      onApplied: () => undefined,
      onStatus: () => undefined,
    });
    queue.reset(1);
    queue.enqueue(editedDraft("invalid"));
    await setImmediate();
    queue.enqueue(editedDraft("corrected"));
    await setImmediate();
    assert.deepEqual(calls, ["invalid", "corrected"]);
  });

  it("drops an obsolete queued edit when the user returns to the in-flight draft", async () => {
    let release!: (result: SaveSettingsResult) => void;
    const calls: string[] = [];
    const queue = new SettingsSaveQueue({
      api: {
        saveSettings: async (draft) => {
          calls.push(draft.memory.engine);
          return new Promise<SaveSettingsResult>((resolve) => { release = resolve; });
        },
        readSettings: async () => ({ configPath: "config.toml", formData: editedDraft("first"), generation: 2 }),
      },
      onApplied: () => undefined,
      onStatus: () => undefined,
    });
    queue.reset(1);
    queue.enqueue(editedDraft("first"));
    queue.enqueue(editedDraft("obsolete"));
    queue.enqueue(editedDraft("first"));
    release({ ok: true, generation: 2 });
    await setImmediate();
    assert.deepEqual(calls, ["first"]);
  });

  it("restores the persisted value instead of saving an obsolete intermediate draft", async () => {
    let release!: (result: SaveSettingsResult) => void;
    const calls: string[] = [];
    let persisted = editedDraft("original");
    const queue = new SettingsSaveQueue({
      api: {
        saveSettings: async (draft) => {
          calls.push(draft.memory.engine);
          persisted = draft;
          if (calls.length === 1) return new Promise<SaveSettingsResult>((resolve) => { release = resolve; });
          return { ok: true, generation: 3 };
        },
        readSettings: async () => ({ configPath: "config.toml", formData: persisted, generation: calls.length + 1 }),
      },
      onApplied: () => undefined,
      onStatus: () => undefined,
    });
    queue.reset(1);
    const original = editedDraft("original");
    queue.enqueue(editedDraft("first"), original);
    queue.enqueue(editedDraft("obsolete"), original);
    queue.enqueue(original, original);
    release({ ok: true, generation: 2 });
    await setImmediate();
    assert.deepEqual(calls, ["first", "original"]);
  });
});
