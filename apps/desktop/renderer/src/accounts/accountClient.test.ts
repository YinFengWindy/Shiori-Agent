import assert from "node:assert/strict";
import { test } from "node:test";
import { createAccountClient } from "./accountClient";

test("account client maps host snapshots and sends only explicit rule mutations", async () => {
  const calls: Array<{ method: string; payload: Record<string, unknown> }> = [];
  const row = {
    id: "a", plugin_id: "demo", platform: "demo", platform_account_id: "101",
    display_name: "Account", avatar_url: "", role_id: null,
    plugin_enabled: true, runtime_active: true, connection: "online", capabilities: [], error: "",
    response_rules: { private_enabled: true, group_enabled: true, require_mention: true,
      blocked_sender_ids: [], group_rules: [{ chat_id: "group-1", enabled: true,
        require_mention: false, blocked_sender_ids: ["sender-1"] }] },
  };
  const client = createAccountClient(async ({ method, payload }) => {
    calls.push({ method, payload });
    return { id: "r", type: "response", method, error: null,
      payload: method === "accounts.list" ? { accounts: [row] } : { account: row } };
  });
  const [account] = await client.list();
  assert.equal(account.responseRules.groupRules[0].chatId, "group-1");
  assert.equal(account.responseRules.groupRules[0].blockedSenderIds[0], "sender-1");
  assert.deepEqual(calls.map(({ method }) => method), ["accounts.list"]);
  await client.assign("a", "role-1");
  await client.setRules("a", account.responseRules);
  assert.deepEqual(calls[2], { method: "accounts.rules.set", payload: {
    account_id: "a", response_rules: { private_enabled: true, group_enabled: true,
      require_mention: true, blocked_sender_ids: [], group_rules: [{ chat_id: "group-1",
        enabled: true, require_mention: false, blocked_sender_ids: ["sender-1"] }] },
  } });
});
