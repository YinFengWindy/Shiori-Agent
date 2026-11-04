import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { useMcpServers } from "./useMcpServers";
import { useMcpOAuth } from "./useMcpOAuth";
import type { McpServer, McpSnapshot } from "./types";

function snapshot(operation: McpServer["operation"]): McpSnapshot {
  return { instance_id: "fixture", loading: false, error: null, servers: [{
    id: "server", label: "Server", revision: 1, enabled: true,
    transport: { kind: "streamable_http", auth: "oauth" },
    command_configured: false, env_names: [], url_configured: true, bearer_configured: false, header_names: [],
    oauth: { status: "authorized", redirect_uri: "http://127.0.0.1:43819/callback", client_configured: false },
    selection: { mode: "all", names: [] }, status: "connected", error: null, tools: [], operation,
  }] };
}

test("an earlier terminal login and stale event reads cannot consume a new browser request", async () => {
  let current = snapshot({ id: "previous", kind: "login", status: "succeeded", error: null });
  let resolveLogin: ((value: McpSnapshot) => void) | undefined;
  let notify = () => {};
  const client = createFakePluginClient({
    events: { on: async (_name, handler) => {
      notify = () => handler({}, { id: "event", type: "event", method: "servers.changed", payload: {} });
      return () => {};
    } },
    call: async <T,>(method: string) => {
      if (method === "servers.list") return current as T;
      assert.equal(method, "servers.login");
      return await new Promise<McpSnapshot>((resolve) => { resolveLogin = resolve; }) as T;
    },
  });
  const fake = createFakeHostServices();
  function Probe() {
    const state = useMcpServers(client);
    const oauth = useMcpOAuth(state.snapshot, state.run, fake.host);
    return <button disabled={state.busy} onClick={() => { void oauth.login("server"); }}>登录</button>;
  }
  const view = await mountTestComponent(<Probe />);
  try {
    await act(async () => { view.container.querySelector("button")!.click(); });
    assert.equal(view.container.querySelector("button")!.disabled, true);
    // An event during the pending RPC still carries the previous terminal operation.
    await act(async () => { notify(); });
    assert.deepEqual(fake.calls, []);
    current = snapshot({ id: "new", kind: "login", status: "running", error: null, authorization_url: "https://example.test/authorize" });
    await act(async () => { resolveLogin?.(current); });
    await act(async () => { notify(); });
    assert.deepEqual(fake.calls, [{ service: "openExternal", url: "https://example.test/authorize" }]);
    current = snapshot({ id: "new", kind: "login", status: "failed", error: "rejected" });
    await act(async () => { notify(); });
    await act(async () => { view.container.querySelector("button")!.click(); });
    await act(async () => { notify(); });
    current = snapshot({ id: "retry", kind: "login", status: "running", error: null, authorization_url: "https://example.test/retry" });
    await act(async () => { resolveLogin?.(current); });
    assert.deepEqual(fake.calls, [{ service: "openExternal", url: "https://example.test/authorize" }, { service: "openExternal", url: "https://example.test/retry" }]);
  } finally { await view.cleanup(); }
});
