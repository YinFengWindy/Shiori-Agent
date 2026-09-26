import assert from "node:assert/strict";
import { it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../testing/domTestHarness";
import { initialSemanticQuery, type RoleSemanticList } from "./roleSemanticMemory";
import { useRoleSemanticMemory } from "./useRoleSemanticMemory";

it("does not show a stale role response after a role switch", async () => {
  const pending: Record<string, (value: RoleSemanticList) => void> = {};
  const readList = (roleId: string) => new Promise<RoleSemanticList>((resolve) => { pending[roleId] = resolve; });
  const readDetail = async () => ({ role_id: "mira", status: "ready" as const, item: null });
  function Harness({ roleId }: { roleId: string }) {
    const state = useRoleSemanticMemory(roleId, true, initialSemanticQuery, "", readList, readDetail);
    return <p>{state.listLoading ? "loading" : state.list?.items[0]?.summary ?? state.listError}</p>;
  }
  const view = await mountTestComponent(<Harness roleId="mira" />);
  try {
    await view.render(<Harness roleId="atlas" />);
    await act(async () => pending.mira({ role_id: "mira", status: "ready", items: [{ id: "m1", summary: "Mira secret" }], total: 1 }));
    assert.doesNotMatch(view.container.textContent ?? "", /Mira secret/);
    await act(async () => pending.atlas({ role_id: "atlas", status: "ready", items: [{ id: "a1", summary: "Atlas memory" }], total: 1 }));
    assert.match(view.container.textContent ?? "", /Atlas memory/);
  } finally {
    await view.cleanup();
  }
});
