import assert from "node:assert/strict";
import { before, test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { refreshPluginEnabledState, resetPluginEnabledStateForTests } from "./pluginEnabledStateStore";

let PluginTrustHost: typeof import("./PluginTrustHost").PluginTrustHost;
let PluginManagementSection: typeof import("./PluginManagementSection").PluginManagementSection;
before(async () => {
  const view = await mountTestComponent(null);
  ({ PluginTrustHost } = await import("./PluginTrustHost"));
  ({ PluginManagementSection } = await import("./PluginManagementSection"));
  await view.cleanup();
});

function button(text: string) {
  const result = Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find((item) => item.textContent === text);
  assert.ok(result, `missing button: ${text}`);
  return result;
}

async function fixture({ enabled = true, lostResponse = false } = {}) {
  resetPluginEnabledStateForTests();
  let trusted = false;
  let fingerprint = "first";
  let refreshFails = false;
  const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
  const view = await mountTestComponent(null, { windowGlobals: { miraDesktop: {
    applicationSessionId: async () => "host-trust-session",
    onEvent: () => () => undefined,
    invoke: async (request: { method: string; payload: Record<string, unknown> }) => {
      requests.push(request);
      if (request.method === "plugins.trust") {
        trusted = true;
        if (request.payload.enable === true) enabled = true;
        if (lostResponse) throw new Error("confirmation response lost");
      }
      if (request.method === "plugins.list" && refreshFails) throw new Error("refresh unavailable");
      return { id: "r", type: "response", method: request.method, error: null, payload: { plugins: [{
        id: "example", name: "Example", candidate_id: "workspace/example", source: "workspace", directory: "workspace/example", version: "1", description: "",
        enabled, can_toggle: trusted, state: trusted ? (enabled ? "ACTIVE" : "DISABLED") : "UNTRUSTED", error: "", diagnostic: null,
        has_config_schema: false, channels: [], supports_hot_unload: true,
        can_trust: !trusted, trusted, trust_fingerprint: trusted ? null : fingerprint, content_fingerprint: fingerprint,
      }] } };
    },
  } } });
  return { view, requests, changeContent: () => { fingerprint = "changed"; }, failRefresh: (value: boolean) => { refreshFails = value; } };
}

test("startup asks before settings navigation; cancel stays dismissed through roster refreshes", async () => {
  const { view, requests } = await fixture();
  try {
    await view.render(<PluginTrustHost ready />);
    await act(async () => { await new Promise((done) => setTimeout(done, 0)); });
    const dialog = document.querySelector('[role="dialog"]');
    assert.ok(dialog?.textContent?.includes("Example"));
    assert.ok(dialog?.textContent?.includes("workspace/example"));
    assert.ok(dialog?.querySelector('[data-testid="confirm-persona"]'));
    assert.equal(requests.some((request) => request.method === "plugins.trust"), false);
    await act(async () => button("取消").click());
    await act(async () => { await refreshPluginEnabledState(); });
    assert.equal(document.querySelector('[role="dialog"]'), null);
    assert.equal(requests.some((request) => request.method === "plugins.trust"), false);
  } finally { await view.cleanup(); resetPluginEnabledStateForTests(); }
});

test("disabled candidates wait for explicit enable and use the same trust dialog", async () => {
  const { view, requests } = await fixture({ enabled: false });
  try {
    await view.render(<><PluginManagementSection /><PluginTrustHost ready /></>);
    await act(async () => { await new Promise((done) => setTimeout(done, 0)); });
    assert.equal(document.querySelector('[role="dialog"]'), null);
    const toggle = document.querySelector<HTMLButtonElement>('[role="switch"]');
    assert.ok(toggle && !toggle.disabled);
    await act(async () => toggle.click());
    assert.equal(requests.some((request) => request.method === "plugins.setEnabled"), false);
    await act(async () => button("信任并启用").click());
    assert.equal(requests.find((request) => request.method === "plugins.trust")?.payload.enable, true);
    assert.equal(toggle.getAttribute("aria-checked"), "true");
    assert.equal(document.querySelector('[role="dialog"]'), null);
  } finally { await view.cleanup(); resetPluginEnabledStateForTests(); }
});

test("lost confirmation and failed refresh reconcile by retrying the same operation", async () => {
  const { view, requests, failRefresh } = await fixture({ lostResponse: true });
  try {
    await view.render(<PluginTrustHost ready />);
    await act(async () => { await new Promise((done) => setTimeout(done, 0)); });
    failRefresh(true);
    await act(async () => button("确认信任").click());
    assert.ok(document.querySelector('[role="dialog"]')?.textContent?.includes("无法确认插件当前状态"));
    failRefresh(false);
    await act(async () => button("确认信任").click());
    const confirmations = requests.filter((request) => request.method === "plugins.trust");
    assert.equal(confirmations.length, 2);
    assert.equal(confirmations[0].payload.operation_id, confirmations[1].payload.operation_id);
    assert.equal(document.querySelector('[role="dialog"]'), null);
  } finally { await view.cleanup(); resetPluginEnabledStateForTests(); }
});

test("an open dialog cannot silently approve replacement contents", async () => {
  const { view, requests, changeContent } = await fixture();
  try {
    await view.render(<PluginTrustHost ready />);
    await act(async () => { await new Promise((done) => setTimeout(done, 0)); });
    changeContent();
    await act(async () => { await refreshPluginEnabledState(); });
    assert.equal(button("确认信任").disabled, true);
    assert.equal(requests.some((request) => request.method === "plugins.trust"), false);
    await act(async () => button("取消").click());
    assert.equal(button("确认信任").disabled, false);
    await act(async () => button("确认信任").click());
    assert.equal(requests.find((request) => request.method === "plugins.trust")?.payload.fingerprint, "changed");
  } finally { await view.cleanup(); resetPluginEnabledStateForTests(); }
});
