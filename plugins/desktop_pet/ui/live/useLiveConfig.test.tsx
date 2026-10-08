import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import type { PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { useLiveConfig, type LiveConfigAutosave } from "./useLiveConfig";

function Probe({ client, roleId, onRender }: { client: PluginRpcClient; roleId: string | null; onRender(config: LiveConfigAutosave): void }) {
  onRender(useLiveConfig(client, roleId));
  return null;
}

test("the role's settings load and save under its id, and the backend's stored form is adopted", async () => {
  const requests: Array<{ method: string; payload?: Record<string, unknown> }> = [];
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    requests.push({ method, payload });
    if (method === "live.config.get") return { room_id: 1, reply_interval_seconds: 5, wait_timeout_seconds: 30 } as T;
    return { room_id: 2, reply_interval_seconds: 5, wait_timeout_seconds: 30 } as T;
  } });
  let config: LiveConfigAutosave | null = null;
  const view = await mountTestComponent(<Probe client={client} roleId="role" onRender={(next) => { config = next; }} />);
  try {
    assert.deepEqual(config!.saved, { room_id: 1, reply_interval_seconds: 5, wait_timeout_seconds: 30 });
    await act(async () => config!.commit((current) => ({ ...current, room_id: 2 })));
    assert.deepEqual(requests, [
      { method: "live.config.get", payload: { role_id: "role" } },
      { method: "live.config.set", payload: { room_id: 2, reply_interval_seconds: 5, wait_timeout_seconds: 30, role_id: "role" } },
    ]);
    assert.equal(config!.saved?.room_id, 2);
  } finally { await view.cleanup(); }
});

test("a role not saved yet loads and saves nothing", async () => {
  const client = createFakePluginClient({ call: async () => assert.fail("no request without a role") });
  let config: LiveConfigAutosave | null = null;
  const view = await mountTestComponent(<Probe client={client} roleId={null} onRender={(next) => { config = next; }} />);
  try {
    assert.equal(config!.draft, null);
    assert.equal(config!.loading, false);
  } finally { await view.cleanup(); }
});
