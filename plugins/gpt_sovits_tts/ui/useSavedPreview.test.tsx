import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider, type DraftSavePhase } from "@yinfengwindy/shiori-sdk";
import { createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { useSavedPreview } from "./useSavedPreview";

async function probe() {
  const { host } = createFakeHostServices();
  const events: string[] = [];
  const client = createFakePluginClient({
    services: { list: async () => ({ services: [] }), call: async <T,>(_service: unknown, _method: string, payload?: Record<string, unknown>) => { events.push(`synthesize:${String(payload?.mood)}`); return { audio_base64: "audio", format: "wav" } as T; } },
    background: { call: async <T,>(_name: string, payload?: Record<string, unknown>) => ({ id: payload?.id, role_id: "role", phase: "idle", error: "" }) as T },
  });
  let latest!: ReturnType<typeof useSavedPreview>;
  const commit = () => { events.push("commit"); };
  function Probe({ savePhase }: { savePhase: DraftSavePhase }) { latest = useSavedPreview(client, "role", { savePhase, commit }); return null; }
  const render = (savePhase: DraftSavePhase) => <PluginHostServicesProvider services={host}><Probe savePhase={savePhase} /></PluginHostServicesProvider>;
  const view = await mountTestComponent(render("idle"));
  return { view, events, render, latest: () => latest };
}

test("with nothing pending the preview plays at once", async () => {
  const ui = await probe();
  try {
    await act(async () => ui.latest().play("开心"));
    assert.deepEqual(ui.events, ["synthesize:开心"]);
  } finally { await ui.view.cleanup(); }
});

test("a pending edit is committed first and the preview starts only once the save lands", async () => {
  const ui = await probe();
  try {
    await ui.view.render(ui.render("saving"));
    await act(async () => ui.latest().play(""));
    assert.deepEqual(ui.events, ["commit"]);
    assert.equal(ui.latest().busy, true);
    await ui.view.render(ui.render("idle"));
    assert.deepEqual(ui.events, ["commit", "synthesize:"]);
  } finally { await ui.view.cleanup(); }
});

test("a failed save drops the queued preview and blocks previewing with its reason", async () => {
  const ui = await probe();
  try {
    await ui.view.render(ui.render("saving"));
    await act(async () => ui.latest().play("开心"));
    await ui.view.render(ui.render("error"));
    assert.equal(ui.latest().busy, false);
    assert.equal(ui.latest().blockedReason, "保存失败，暂不能试听");
    await act(async () => ui.latest().play("开心"));
    await ui.view.render(ui.render("idle"));
    assert.deepEqual(ui.events, ["commit"], "nothing plays after the failure, even once a later save succeeds");
  } finally { await ui.view.cleanup(); }
});
