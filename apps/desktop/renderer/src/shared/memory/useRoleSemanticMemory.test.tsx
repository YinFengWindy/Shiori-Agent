import assert from "node:assert/strict";
import { it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../testing/domTestHarness";
import { initialSemanticQuery, type RoleSemanticList, type RoleSemanticQuery } from "./roleSemanticMemory";
import { useRoleSemanticMemory } from "./useRoleSemanticMemory";

const readDetail = async () => ({ role_id: "mira", status: "ready" as const, item: null });

it("does not show a stale role response after a role switch", async () => {
  const pending: Record<string, (value: RoleSemanticList) => void> = {};
  const readList = (roleId: string) => new Promise<RoleSemanticList>((resolve) => { pending[roleId] = resolve; });
  function Harness({ roleId }: { roleId: string }) {
    const state = useRoleSemanticMemory(roleId, true, initialSemanticQuery, "", readList, readDetail);
    return <p>{state.listLoading ? "loading" : state.list?.items[0]?.summary ?? state.listError}</p>;
  }
  const view = await mountTestComponent(<Harness roleId="mira" />);
  try {
    await view.render(<Harness roleId="atlas" />);
    await act(async () => pending.mira({ role_id: "mira", status: "ready", items: [{ id: "m1", summary: "Mira secret" }], total: 1, page: 1, page_size: 20, filters: {} }));
    assert.doesNotMatch(view.container.textContent ?? "", /Mira secret/);
    await act(async () => pending.atlas({ role_id: "atlas", status: "ready", items: [{ id: "a1", summary: "Atlas memory" }], total: 1, page: 1, page_size: 20, filters: {} }));
    assert.match(view.container.textContent ?? "", /Atlas memory/);
  } finally {
    await view.cleanup();
  }
});

it("keeps a role's declared filters while reloading and drops them on role switch", async () => {
  const pending: Array<(value: RoleSemanticList) => void> = [];
  const readList = () => new Promise<RoleSemanticList>((resolve) => { pending.push(resolve); });
  const ready = (roleId: string, types: string[]): RoleSemanticList => ({
    role_id: roleId, status: "ready", items: [], total: 0, page: 1, page_size: 20, filters: { memory_type: types },
  });
  function Harness({ roleId, query }: { roleId: string; query: RoleSemanticQuery }) {
    const state = useRoleSemanticMemory(roleId, true, query, "", readList, readDetail);
    return <p>{state.filters === null ? "undeclared" : state.filters.memory_type?.join(",") ?? "none"}</p>;
  }
  const view = await mountTestComponent(<Harness roleId="mira" query={initialSemanticQuery} />);
  try {
    assert.equal(view.container.textContent, "undeclared");
    await act(async () => pending[0](ready("mira", ["event"])));
    assert.equal(view.container.textContent, "event");
    await view.render(<Harness roleId="mira" query={{ ...initialSemanticQuery, memory_type: "event" }} />);
    assert.equal(view.container.textContent, "event");
    await view.render(<Harness roleId="atlas" query={initialSemanticQuery} />);
    assert.equal(view.container.textContent, "undeclared");
    await act(async () => pending[2]({ role_id: "atlas", status: "disabled", items: [], total: 0 }));
    assert.equal(view.container.textContent, "none");
  } finally {
    await view.cleanup();
  }
});
