import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { useAutoCgPromptSettings } from "./useAutoCgPromptSettings";

test("switching roles saves the old draft to its own RPC identity and loads the new role", async () => {
  const saved = new Map([["mira", "猫耳"], ["rina", "全身构图"]]);
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    const roleId = String(payload?.role_id);
    if (method === "role_settings.set") saved.set(roleId, String(payload?.prompt_instructions));
    else assert.equal(method, "role_settings.get");
    return { prompt_instructions: saved.get(roleId) } as T;
  } });
  let current: ReturnType<typeof useAutoCgPromptSettings> | undefined;
  function Harness({ roleId }: { roleId: string }) {
    current = useAutoCgPromptSettings(client, roleId);
    return null;
  }
  const view = await mountTestComponent(<Harness roleId="mira" />);
  try {
    await act(async () => current!.update(() => ({ prompt_instructions: "保留猫耳" })));
    await view.render(<Harness roleId="rina" />);
    assert.equal(saved.get("mira"), "保留猫耳");
    assert.equal(saved.get("rina"), "全身构图");
    assert.equal(current!.draft?.prompt_instructions, "全身构图");
    await act(async () => current!.commit(() => ({ prompt_instructions: "" })));
    assert.equal(saved.get("rina"), "");
    assert.equal(saved.get("mira"), "保留猫耳");
  } finally { await view.cleanup(); }
});
