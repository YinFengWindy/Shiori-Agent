import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { createFakePluginClient, deferred, mountTestComponent } from "../testing/index";
import { useManagedRuntime, type ManagedRuntimeStatus } from "./useManagedRuntime";

const ready: ManagedRuntimeStatus = { phase: "ready", running: true, installed: true, busy: false, error: "", item: "", received: 0, total: 0, revision: "fixed", reclaimable: 0 };

test("background preparation is polled and unmounting never cancels its backend ownership", async (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  const requests: string[] = [];
  let preparing = false;
  const client = createFakePluginClient({ call: async <T,>(method: string) => {
    requests.push(method);
    if (method === "runtime.prepare") { preparing = true; return { ...ready, busy: true, phase: "preparing" } as T; }
    return { ...ready, busy: preparing } as T;
  } });
  let state!: ReturnType<typeof useManagedRuntime>;
  function Probe() { state = useManagedRuntime(client); return null; }
  const view = await mountTestComponent(<Probe />);
  await act(async () => state.run("prepare"));
  assert.equal(state.status?.busy, true);
  preparing = false;
  await act(async () => context.mock.timers.tick(1000));
  assert.equal(state.status?.busy, false);
  await view.cleanup();
  assert.equal(requests.includes("runtime.cancel"), false);
  const count = requests.length;
  context.mock.timers.tick(5000);
  assert.equal(requests.length, count);
});

test("late client results are discarded and failed actions remain visible", async (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  const previous = deferred<ManagedRuntimeStatus>();
  const oldClient = createFakePluginClient({ call: async <T,>() => previous.promise as Promise<T> });
  const nextClient = createFakePluginClient({ call: async <T,>(method: string) => {
    if (method === "runtime.stop") throw new Error("stop failed");
    return ready as T;
  } });
  let state!: ReturnType<typeof useManagedRuntime>;
  function Probe({ client }: { client: typeof oldClient }) { state = useManagedRuntime(client); return null; }
  const view = await mountTestComponent(<Probe client={oldClient} />);
  try {
    await view.render(<Probe client={nextClient} />);
    await act(async () => previous.resolve({ ...ready, revision: "old" }));
    assert.equal(state.status?.revision, "fixed");
    await act(async () => state.run("stop"));
    assert.match(state.error, /stop failed/);
    assert.equal(state.pending, false);
    await act(async () => context.mock.timers.tick(1000));
    assert.match(state.error, /stop failed/);
  } finally { await view.cleanup(); }
});
