import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { accountStatus } from "./accountPresentation";
import { useAccounts } from "./useAccounts";

test("mounted account views poll fresh runtime status and stop polling on unmount", async () => {
  let connection = "online";
  let calls = 0;
  let tick: (() => void) | undefined;
  let stopped = false;
  function View() {
    const { accounts } = useAccounts();
    return <span>{accounts?.[0] ? accountStatus(accounts[0]) : "加载中"}</span>;
  }
  const view = await mountTestComponent(<View />, { windowGlobals: {
    setInterval: (callback: () => void) => { tick = callback; return 42; },
    clearInterval: (id: number) => { assert.equal(id, 42); stopped = true; },
    miraDesktop: {
      onEvent: () => () => undefined,
      invoke: async ({ method }: { method: string }) => {
        calls += 1;
        return { id: "response", type: "response", method, error: null, payload: { accounts: [{
          id: "a", plugin_id: "demo", platform: "demo", platform_account_id: "1", display_name: "",
          avatar_url: "", role_id: null, plugin_enabled: true, runtime_active: true, connection,
          capabilities: [], error: "", response_rules: { private_enabled: true, group_enabled: true,
            require_mention: true, blocked_sender_ids: [], group_rules: [] },
        }] } };
      },
    },
  } });
  try {
    assert.match(view.container.textContent ?? "", /在线/);
    assert.ok(tick);
    connection = "offline";
    await act(async () => tick?.());
    assert.match(view.container.textContent ?? "", /离线/);
    assert.equal(calls, 2);
  } finally { await view.cleanup(); }
  assert.equal(stopped, true);
});
