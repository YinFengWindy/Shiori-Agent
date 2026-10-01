import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import type { BridgeEvent } from "@shiori/sdk";
import { mountTestComponent } from "@shiori/sdk/testing";
import { accountStatusView } from "@shiori/sdk/host-internal";
import { useAccounts } from "./useAccounts";

test("mounted account views reload when the host pushes an account change", async () => {
  let connection = "login_required";
  let calls = 0;
  let emit: ((event: BridgeEvent) => void) | undefined;
  let unsubscribed = false;
  function View() {
    const { accounts } = useAccounts();
    return <span>{accounts?.[0] ? accountStatusView(accounts[0]).label : "加载中"}</span>;
  }
  const view = await mountTestComponent(<View />, { windowGlobals: {
    miraDesktop: {
      onEvent: (listener: (event: BridgeEvent) => void) => {
        emit = listener;
        return () => { unsubscribed = true; };
      },
      invoke: async ({ method }: { method: string }) => {
        calls += 1;
        return { id: "response", type: "response", method, error: null, payload: { accounts: [{
          id: "a", plugin_id: "demo", platform: "demo", platform_account_id: "1", display_name: "",
          avatar_url: "", role_id: "role-1", runtime_active: true, connection,
          capabilities: [], error: "", response_rules: { private_enabled: true, group_enabled: true,
            blocked_sender_ids: [] },
        }] } };
      },
    },
  } });
  try {
    assert.match(view.container.textContent ?? "", /需要登录/);
    assert.ok(emit);
    connection = "online";
    await act(async () => emit?.({ id: "accounts.updated", type: "event", method: "accounts.updated", payload: { account_id: "a" } }));
    assert.match(view.container.textContent ?? "", /在线/);
    await act(async () => emit?.({ id: "x", type: "event", method: "session.updated", payload: {} }));
    assert.equal(calls, 2);
  } finally { await view.cleanup(); }
  assert.equal(unsubscribed, true);
});
