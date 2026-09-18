import assert from "node:assert/strict";
import { test } from "node:test";
import { createPluginPackageClient } from "./pluginPackageClient";
import type { DesktopInvoke } from "../shared/bridgeInvoke";

test("formal installs require explicit trust and uninstalls send an independent data choice", async () => {
  const requests: Parameters<DesktopInvoke>[0][] = [];
  const invoke: DesktopInvoke = async (request) => {
    requests.push(request);
    return { id: "r", type: "response", method: request.method, error: null, payload: {} };
  };
  const client = createPluginPackageClient(invoke);
  await client.cancel("cancel-token");
  await client.confirm("confirmed-token");
  await client.uninstall("workspace/demo", false);
  await client.uninstall("workspace/demo", true);
  assert.deepEqual(requests[0], { method: "plugins.install.cancel", payload: { token: "cancel-token" } });
  assert.deepEqual(requests[1], { method: "plugins.install.confirm", payload: { token: "confirmed-token", trusted: true } });
  assert.equal(requests[2].payload.delete_data, false);
  assert.equal(requests[3].payload.delete_data, true);
  assert.equal(requests[3].payload.candidate_id, "workspace/demo");
  assert.notEqual(requests[2].payload.operation_id, requests[3].payload.operation_id);
});
