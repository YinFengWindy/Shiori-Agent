import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@shiori/sdk/testing";

test("role deletion waits for its account list and can retry a failed lookup", async () => {
  const requests: Array<(response: Record<string, unknown>) => void> = [];
  const environment = await mountTestComponent(null);
  const { useRoleDeletionAccounts } = await import("./useRoleDeletionAccounts");
  await environment.cleanup();
  function Probe() {
    const result = useRoleDeletionAccounts("mira");
    return <><output>{result.status}:{result.accounts.length}:{result.error}</output>
      <button type="button" onClick={result.retry}>重试</button></>;
  }
  const view = await mountTestComponent(<Probe />, { windowGlobals: { miraDesktop: {
    onEvent: () => () => undefined,
    invoke: () => new Promise((resolve) => requests.push(resolve)),
  } } });
  try {
    assert.equal(view.container.querySelector("output")?.textContent, "loading:0:");
    await act(async () => requests[0]({ id: "r", type: "response", method: "accounts.list",
      error: { code: "unavailable", message: "bridge down", details: {} }, payload: null }));
    assert.equal(view.container.querySelector("output")?.textContent, "error:0:bridge down");
    await act(async () => view.container.querySelector("button")?.click());
    assert.equal(view.container.querySelector("output")?.textContent, "loading:0:");
    await act(async () => requests[1]({ id: "r", type: "response", method: "accounts.list", error: null,
      payload: { accounts: [{ id: "telegram:1", role_id: "mira", plugin_id: "telegram", platform: "telegram",
        platform_account_id: "1", config_ref: "1", display_name: "", avatar_url: "", runtime_active: true,
        connection: "online", capabilities: [], error: "", response_rules: {
          private_enabled: true, group_enabled: true, blocked_sender_ids: [],
        } }] } }));
    assert.equal(view.container.querySelector("output")?.textContent, "ready:1:");
  } finally { await view.cleanup(); }
});
