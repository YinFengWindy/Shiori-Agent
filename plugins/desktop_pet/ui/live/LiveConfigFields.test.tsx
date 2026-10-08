import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import type { PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { changeInputValue, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { LiveConfig } from "./liveContracts";
import { LiveConfigFields } from "./LiveConfigFields";
import { useLiveConfig } from "./useLiveConfig";

function Fields({ client }: { client: PluginRpcClient }) {
  const config = useLiveConfig(client, "role");
  return config.draft ? <LiveConfigFields draft={config.draft} update={config.update} disabled={false} /> : null;
}

test("valid edits autosave the whole document for the role once typing pauses; invalid text is never sent", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const saves: Array<Record<string, unknown> | undefined> = [];
  let stored: LiveConfig = { room_id: null, reply_interval_seconds: 5, wait_timeout_seconds: 30 };
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    if (method === "live.config.get") return structuredClone(stored) as T;
    if (method === "live.config.set") { saves.push(payload); const config = { ...payload }; delete config.role_id; stored = config as LiveConfig; return structuredClone(stored) as T; }
    throw new Error(`unexpected ${method}`);
  } });
  const view = await mountTestComponent(<Fields client={client} />);
  const input = (label: string) => view.container.querySelector<HTMLInputElement>(`[aria-label="${label}"]`)!;
  try {
    assert.equal(input("直播间号").value, "");
    assert.equal(input("回复间隔（秒）").value, "5");
    assert.equal(input("等待时限（秒）").value, "30");

    await changeInputValue(input("等待时限（秒）"), "4");
    assert.equal(input("等待时限（秒）").getAttribute("aria-invalid"), "true");
    await changeInputValue(input("回复间隔（秒）"), "301");
    await act(async () => t.mock.timers.tick(5000));
    assert.deepEqual(saves, [], "out-of-range values are never written");

    await changeInputValue(input("直播间号"), "21452505");
    await changeInputValue(input("回复间隔（秒）"), "0");
    await act(async () => t.mock.timers.tick(5000));
    assert.deepEqual(saves, [{ room_id: 21452505, reply_interval_seconds: 0, wait_timeout_seconds: 30, role_id: "role" }]);
  } finally { await view.cleanup(); }
});
