import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import type { BridgeEvent } from "@shiori/plugin-sdk";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { mountTestComponent } from "@shiori/plugin-sdk/testing";

type Request = { method: string; payload: Record<string, unknown> };

const identity = (id: string, scope: string, accountId = "") => ({
  id, plugin_id: "qq", user_id: `10${id}`, scope, account_id: accountId, bound_at: "2026-09-29T08:00:00+00:00",
});
const account = {
  id: "acc-1", plugin_id: "qq", platform: "qq", platform_account_id: "900", config_ref: "", display_name: "小栞",
  avatar_url: "", role_id: "role-1", runtime_active: true, connection: "online", capabilities: [], error: "",
  response_rules: { private_enabled: true, group_enabled: true, require_mention: true, blocked_sender_ids: [] },
};

/** A fake host: `identities` is what `identities.list` returns now; every call is recorded. */
function host(identities: Array<ReturnType<typeof identity>>) {
  const state = { identities, calls: [] as Request[], listeners: [] as Array<(event: BridgeEvent) => void> };
  const payloads: Record<string, () => unknown> = {
    "identities.list": () => ({ identities: state.identities }),
    "identities.pairing.create": () => ({ code: "ABCD2345", expires_at: new Date(Date.now() + 600_500).toISOString() }),
    "identities.unbind": () => ({}),
    "accounts.list": () => ({ accounts: [account] }),
  };
  const miraDesktop = {
    onEvent: (listener: (event: BridgeEvent) => void) => {
      state.listeners.push(listener);
      return () => { state.listeners = state.listeners.filter((item) => item !== listener); };
    },
    invoke: async (request: Request) => {
      state.calls.push(request);
      return { id: "r", type: "response", method: request.method, error: null, payload: payloads[request.method]() };
    },
  };
  const updated = () => act(async () => {
    for (const listener of state.listeners) listener({ id: "e", type: "event", method: "identities.updated", payload: {} });
  });
  return { state, updated, options: { windowGlobals: { miraDesktop } } };
}

async function loadSection() {
  const environment = await mountTestComponent(null);
  const { IdentitySettingsSection } = await import("./IdentitySettingsSection");
  await environment.cleanup();
  pluginUiRegistry.registerAccountDetail({ slot: "account.detail", pluginId: "qq", label: "QQ", Component: () => null });
  return IdentitySettingsSection;
}

const buttonNamed = (root: ParentNode | null, name: string) =>
  Array.from(root?.querySelectorAll("button") ?? []).find((button) => button.textContent === name);

test("bound identities list their channel, scope and bind time, and reload on identities.updated", async () => {
  const Section = await loadSection();
  const fake = host([identity("1", "platform")]);
  const view = await mountTestComponent(<Section />, fake.options);
  try {
    const rows = () => Array.from(view.container.querySelectorAll("li")).map((item) => item.textContent ?? "");
    assert.equal(rows().length, 1);
    assert.match(rows()[0], /^QQ101全平台 · .+解除绑定$/);
    fake.state.identities = [identity("1", "platform"), identity("2", "account", "acc-1"), identity("3", "account", "gone")];
    await fake.updated();
    assert.match(rows()[1], /^QQ102仅 小栞 · /);
    assert.match(rows()[2], /^QQ103仅 gone · /);
  } finally {
    await view.cleanup();
    pluginUiRegistry.unregisterPlugin("qq");
  }
});

test("the shown pairing code goes away once a new identity arrives", async () => {
  const Section = await loadSection();
  const fake = host([]);
  const view = await mountTestComponent(<Section />, fake.options);
  const code = () => view.container.querySelector('[data-testid="pairing-code"]')?.textContent;
  try {
    // Empty: only the generate action.
    assert.equal(view.container.querySelector("li"), null);
    await act(async () => buttonNamed(view.container, "生成配对码")?.click());
    assert.equal(code(), "ABCD2345");
    assert.equal(view.container.querySelector('[role="timer"]')?.textContent, "10:00");
    // A newly known chat alone does not consume it.
    await fake.updated();
    assert.equal(code(), "ABCD2345");
    fake.state.identities = [identity("1", "platform")];
    await fake.updated();
    assert.equal(code(), undefined);
    assert.ok(buttonNamed(view.container, "生成配对码"));
    // Re-pairing the same identity refreshes its bind time, which consumes the code too.
    await act(async () => buttonNamed(view.container, "生成配对码")?.click());
    assert.equal(code(), "ABCD2345");
    fake.state.identities = [{ ...identity("1", "platform"), bound_at: "2026-09-29T08:10:00+00:00" }];
    await fake.updated();
    assert.equal(code(), undefined);
  } finally {
    await view.cleanup();
    pluginUiRegistry.unregisterPlugin("qq");
  }
});

test("unbinding asks for confirmation before calling the host", async () => {
  const Section = await loadSection();
  const fake = host([identity("1", "platform")]);
  const view = await mountTestComponent(<Section />, fake.options);
  const unbinds = () => fake.state.calls.filter((call) => call.method === "identities.unbind");
  try {
    await act(async () => buttonNamed(view.container, "解除绑定")?.click());
    const dialog = document.querySelector('[role="dialog"]');
    assert.match(dialog?.textContent ?? "", /QQ 101/);
    assert.equal(unbinds().length, 0);
    await act(async () => buttonNamed(dialog, "解除绑定")?.click());
    assert.deepEqual(unbinds().map((call) => call.payload), [{ identity_id: "1" }]);
  } finally {
    await view.cleanup();
    pluginUiRegistry.unregisterPlugin("qq");
  }
});
