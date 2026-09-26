import assert from "node:assert/strict";
import { it } from "node:test";
import { act } from "react";
import type { RoleMemoryDocumentsPayload } from "../types";
import { mountTestComponent } from "../testing/domTestHarness";
import { useRoleMemoryDocuments } from "./useRoleMemoryDocuments";

it("refreshes and ignores an old role response", async () => {
  let resolveMira: ((payload: RoleMemoryDocumentsPayload) => void) | undefined;
  const calls: string[] = [];
  const read = (roleId: string) => {
    calls.push(roleId);
    return roleId === "mira"
      ? new Promise<RoleMemoryDocumentsPayload>((resolve) => { resolveMira = resolve; })
      : Promise.resolve({ role_id: "luna", documents: [{ name: "SELF.md" as const, status: "ready" as const, content: "Luna" }] });
  };
  function Probe({ roleId }: { roleId: string }) {
    const state = useRoleMemoryDocuments(roleId, true, read);
    return <div><p>{state.documents[0]?.content ?? (state.loading ? "loading" : state.error)}</p><button onClick={state.refresh}>Refresh</button></div>;
  }
  const view = await mountTestComponent(<Probe roleId="mira" />);
  try {
    await view.render(<Probe roleId="luna" />);
    assert.match(view.container.textContent ?? "", /Luna/);
    await act(async () => resolveMira?.({ role_id: "mira", documents: [{ name: "SELF.md", status: "ready", content: "Mira" }] }));
    assert.doesNotMatch(view.container.textContent ?? "", /Mira/);
    await act(async () => view.container.querySelector("button")?.click());
    assert.deepEqual(calls, ["mira", "luna", "luna"]);
  } finally {
    await view.cleanup();
  }
});
