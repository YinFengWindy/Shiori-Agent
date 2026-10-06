import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { createFakePluginClient, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { usePrivateDraft } from "./usePrivateDraft";

test("role changes discard late reads and failed saves retain the dirty private draft", async () => {
  const oldRead = deferred<{ value: string }>(); const dirty: boolean[] = [];
  const client = createFakePluginClient();
  let latest!: ReturnType<typeof usePrivateDraft<{ value: string }>>;
  function Probe({ role }: { role: string }) {
    latest = usePrivateDraft(client, role, {
      load: () => role === "old" ? oldRead.promise : Promise.resolve({ value: "next" }),
      save: async () => { throw new Error("private save failed"); }, onDirtyChange: (value) => dirty.push(value),
    });
    return <span>{latest.draft?.value ?? "loading"}</span>;
  }
  const view = await mountTestComponent(<Probe role="old" />);
  try {
    await view.render(<Probe role="next" />);
    await act(async () => oldRead.resolve({ value: "old" }));
    assert.equal(view.container.textContent, "next");
    await act(async () => latest.setDraft({ value: "edited" }));
    await act(async () => latest.save());
    assert.equal(latest.draft?.value, "edited"); assert.equal(latest.dirty, true);
    assert.equal(dirty.at(-1), true); assert.match(latest.error, /private save failed/);
  } finally { await view.cleanup(); }
});

test("read failures and a missing role never produce a saveable default document", async () => {
  const client = createFakePluginClient(); let reads = 0; let saves = 0;
  let latest!: ReturnType<typeof usePrivateDraft<{ value: string }>>;
  function Probe({ role }: { role: string | null }) {
    latest = usePrivateDraft<{ value: string }>(client, role, { load: async () => { reads++; throw new Error("private read failed"); }, save: async (value) => { saves++; return value; } });
    return null;
  }
  const view = await mountTestComponent(<Probe role={null} />);
  try {
    assert.equal(reads, 0); await view.render(<Probe role="role" />);
    assert.equal(latest.draft, null); assert.match(latest.error, /private read failed/);
    await act(async () => latest.save()); assert.equal(saves, 0);
  } finally { await view.cleanup(); }
});

test("a save finishing after a role switch cannot replace the new role draft or clear its dirty state", async () => {
  const pendingSave = deferred<{ value: string }>();
  const client = createFakePluginClient();
  let latest!: ReturnType<typeof usePrivateDraft<{ value: string }>>;
  function Probe({ role }: { role: string }) {
    latest = usePrivateDraft(client, role, {
      load: async () => ({ value: role }),
      save: () => pendingSave.promise,
    });
    return null;
  }
  const view = await mountTestComponent(<Probe role="old" />);
  try {
    await act(async () => latest.setDraft({ value: "old edit" }));
    let save!: Promise<void>;
    await act(async () => { save = latest.save(); });
    await view.render(<Probe role="next" />);
    await act(async () => latest.setDraft({ value: "next edit" }));
    await act(async () => { pendingSave.resolve({ value: "old saved" }); await save; });
    assert.equal(latest.draft?.value, "next edit");
    assert.equal(latest.dirty, true);
    assert.equal(latest.saving, false);
  } finally { await view.cleanup(); }
});
