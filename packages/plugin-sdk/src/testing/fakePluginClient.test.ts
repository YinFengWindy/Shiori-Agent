import assert from "node:assert/strict";
import { test } from "node:test";
import { createFakePluginClient } from "./fakePluginClient";

test("the fake client answers through the given call and rejects every request it was not given", async () => {
  const client = createFakePluginClient({ call: async <T,>(name: string) => ({ name }) as T });
  assert.deepEqual(await client.call("accounts.settings"), { name: "accounts.settings" });
  await assert.rejects(client.events.on("status", () => undefined), /events\.on is not faked/);
  await assert.rejects(client.background.call("sync"), /background\.call is not faked/);
  await assert.rejects(client.dependency("qq"), /dependency is not faked/);
  await assert.rejects(createFakePluginClient().call("accounts.settings"), /call is not faked/);
  await client.dispose();
});
