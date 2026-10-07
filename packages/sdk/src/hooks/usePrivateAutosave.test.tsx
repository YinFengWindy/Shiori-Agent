import assert from "node:assert/strict";
import { test, type TestContext } from "node:test";
import { act, useState } from "react";
import { createFakePluginClient, deferred, mountTestComponent } from "../testing/index";
import type { PluginRpcClient } from "../rpc";
import { usePrivateAutosave, type PrivateAutosaveOptions } from "./usePrivateAutosave";

type Doc = { value: string };
type Autosave = ReturnType<typeof usePrivateAutosave<Doc>>;

/** Mounts the hook for one scope; `options(identity)` supplies that scope's operations. */
async function mountAutosave(options: (identity: string) => PrivateAutosaveOptions<Doc>, identity = "settings", client: PluginRpcClient = createFakePluginClient()) {
  const probe = { latest: undefined as unknown as Autosave, setScope: undefined as unknown as (scope: string) => void };
  function Probe() {
    const [scope, setScope] = useState(identity);
    probe.setScope = setScope;
    probe.latest = usePrivateAutosave(client, scope, options(scope));
    return null;
  }
  const view = await mountTestComponent(<Probe />);
  return { probe, view, switchTo: (scope: string) => act(async () => probe.setScope(scope)) };
}

const edit = (value: string) => () => ({ value });
const tick = (t: TestContext, ms: number) => act(async () => t.mock.timers.tick(ms));

test("consecutive edits save the latest draft once after the quiet period, and an edit made during a save is saved after it", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const saves: string[] = []; const pending: Array<ReturnType<typeof deferred<Doc>>> = [];
  const { probe, view } = await mountAutosave(() => ({
    load: async () => ({ value: "a" }),
    save: (doc) => { saves.push(doc.value); const write = deferred<Doc>(); pending.push(write); return write.promise; },
  }));
  try {
    await act(async () => probe.latest.update(edit("b")));
    await tick(t, 300);
    await act(async () => probe.latest.update(edit("bc")));
    await tick(t, 399);
    assert.deepEqual(saves, []);
    assert.equal(probe.latest.savePhase, "saving");
    await tick(t, 1);
    assert.deepEqual(saves, ["bc"]);

    await act(async () => probe.latest.update(edit("bcd")));
    await tick(t, 400);
    assert.deepEqual(saves, ["bc"], "saves never overlap");
    await act(async () => pending[0].resolve({ value: "bc" }));
    assert.deepEqual(saves, ["bc", "bcd"]);
    assert.equal(probe.latest.draft?.value, "bcd", "an older acknowledgement never replaces a newer edit");
    await act(async () => pending[1].resolve({ value: "bcd" }));
    assert.equal(probe.latest.savePhase, "idle");
    assert.equal(probe.latest.saved?.value, "bcd");
  } finally { await view.cleanup(); }
});

test("switching scope submits the last draft to its own scope and discards that scope's late result; unmounting submits too", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const saves: Array<[string, string]> = []; const oldWrite = deferred<Doc>();
  const { probe, view, switchTo } = await mountAutosave((scope) => ({
    load: async () => ({ value: `${scope} stored` }),
    save: (doc) => { saves.push([scope, doc.value]); return scope === "old" ? oldWrite.promise : Promise.resolve(doc); },
  }), "old");
  try {
    await act(async () => probe.latest.update(edit("old edit")));
    await switchTo("next");
    assert.deepEqual(saves, [["old", "old edit"]], "the scheduled draft is saved at once with its own scope's operations");
    await act(async () => oldWrite.resolve({ value: "old edit" }));
    assert.equal(probe.latest.draft?.value, "next stored");
    assert.equal(probe.latest.saved?.value, "next stored");
    assert.equal(probe.latest.savePhase, "idle");

    await act(async () => probe.latest.update(edit("next edit")));
  } finally { await view.cleanup(); }
  assert.deepEqual(saves, [["old", "old edit"], ["next", "next edit"]]);
});

test("a failed save keeps the draft and pauses autosave; an edit made meanwhile is kept and saved after retry resubmits the failed draft", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const saves: string[] = []; let fail = true;
  const { probe, view } = await mountAutosave(() => ({
    load: async () => ({ value: "stored" }),
    save: async (doc) => { saves.push(doc.value); if (fail) throw new Error("private write failed"); return doc; },
  }));
  try {
    await act(async () => probe.latest.update(edit("first")));
    await tick(t, 400);
    assert.equal(probe.latest.savePhase, "error");
    assert.match(probe.latest.saveError, /private write failed/);
    assert.equal(probe.latest.draft?.value, "first");

    await act(async () => probe.latest.update(edit("second")));
    await tick(t, 400);
    assert.deepEqual(saves, ["first"], "autosave stays paused after a failure");
    assert.equal(probe.latest.draft?.value, "second", "the paused edit is kept");
    assert.equal(probe.latest.savePhase, "error");

    fail = false;
    await act(async () => probe.latest.retry());
    assert.deepEqual(saves, ["first", "first", "second"]);
    assert.equal(probe.latest.savePhase, "idle");
    assert.equal(probe.latest.saved?.value, "second");
  } finally { await view.cleanup(); }
});

test("a failed read never saves a default and reload reads the document again", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let reads = 0; const saves: string[] = [];
  const { probe, view } = await mountAutosave(() => ({
    load: async () => { reads += 1; if (reads === 1) throw new Error("private read failed"); return { value: "stored" }; },
    save: async (doc) => { saves.push(doc.value); return doc; },
  }));
  try {
    assert.match(probe.latest.loadError, /private read failed/);
    const draft = () => probe.latest.draft;
    assert.equal(draft(), null);
    await act(async () => probe.latest.update(edit("default")));
    await act(async () => probe.latest.commit());
    await tick(t, 400);
    assert.deepEqual(saves, []);

    await act(async () => probe.latest.reload());
    assert.equal(probe.latest.loadError, "");
    assert.equal(draft()?.value, "stored");
  } finally { await view.cleanup(); }
  assert.deepEqual(saves, []);
});

test("commit saves a blur/Enter value at once without waiting for the quiet period", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const saves: string[] = [];
  const { probe, view } = await mountAutosave(() => ({
    load: async () => ({ value: "Ctrl+Space" }),
    save: async (doc) => { saves.push(doc.value); return doc; },
  }));
  try {
    await act(async () => probe.latest.commit(edit("Alt+Space")));
    assert.deepEqual(saves, ["Alt+Space"]);
    assert.equal(probe.latest.saved?.value, "Alt+Space");
    await tick(t, 1000);
    assert.deepEqual(saves, ["Alt+Space"]);
  } finally { await view.cleanup(); }
});

test("reload drops the edit scheduled in the quiet period, so no stale save lands after the new read", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const saves: string[] = []; let reads = 0;
  const { probe, view } = await mountAutosave(() => ({
    load: async () => { reads += 1; return { value: `read ${reads}` }; },
    save: async (doc) => { saves.push(doc.value); return doc; },
  }));
  try {
    await act(async () => probe.latest.update(edit("stale")));
    await tick(t, 200);
    await act(async () => probe.latest.reload());
    await tick(t, 1000);
    assert.deepEqual(saves, []);
    assert.equal(probe.latest.draft?.value, "read 2");
    assert.equal(probe.latest.savePhase, "idle");
  } finally { await view.cleanup(); }
  assert.deepEqual(saves, []);
});

test("reload does nothing while a save is in flight", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let reads = 0; const write = deferred<Doc>();
  const { probe, view } = await mountAutosave(() => ({
    load: async () => { reads += 1; return { value: "stored" }; },
    save: () => write.promise,
  }));
  try {
    await act(async () => probe.latest.commit(edit("edited")));
    await act(async () => probe.latest.reload());
    assert.equal(reads, 1);
    await act(async () => write.resolve({ value: "edited" }));
    assert.equal(probe.latest.saved?.value, "edited");
  } finally { await view.cleanup(); }
});

test("a scope change in the same update as a reload still submits the old scope's scheduled edit", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const saves: Array<[string, string]> = [];
  const { probe, view } = await mountAutosave((scope) => ({
    load: async () => ({ value: `${scope} stored` }),
    save: async (doc) => { saves.push([scope, doc.value]); return doc; },
  }), "old");
  try {
    await act(async () => probe.latest.update(edit("old edit")));
    await act(async () => { probe.latest.reload(); probe.setScope("next"); });
    assert.deepEqual(saves, [["old", "old edit"]]);
    assert.equal(probe.latest.draft?.value, "next stored");
  } finally { await view.cleanup(); }
});
