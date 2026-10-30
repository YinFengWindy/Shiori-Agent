/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleTask } from "../shared/types";
import { blockPanelView, groupRoleTasks, reconcileRoleTaskPanelView } from "./roleTaskPanelState";

function createTask(id: string, kind: RoleTask["kind"]): RoleTask {
  return {
    id,
    role_id: "mira",
    kind,
    status: "running",
    label: id,
    detail: id,
    created_at: "",
    cancellable: kind !== "memory_maintenance",
  };
}

describe("roleTaskPanelState", () => {
  it("keeps both host task groups, in sidebar order, even when empty", () => {
    assert.deepEqual(
      groupRoleTasks([createTask("memory", "memory_maintenance")]).map((group) => [group.kind, group.tasks.length]),
      [["subagent", 0], ["memory_maintenance", 1]],
    );
  });

  it("hands the panel to the plugin block for any of its views and returns to the list on an empty one", () => {
    assert.deepEqual(blockPanelView("detail:job-1"), { kind: "block", blockView: "detail:job-1" });
    assert.deepEqual(blockPanelView(""), { kind: "list" });
  });

  it("leaves a host task's details once the task disappears", () => {
    const task = createTask("subagent", "subagent");
    assert.deepEqual(reconcileRoleTaskPanelView({ kind: "detail", taskId: "subagent" }, [task]), { kind: "detail", taskId: "subagent" });
    assert.deepEqual(reconcileRoleTaskPanelView({ kind: "detail", taskId: "subagent" }, []), { kind: "list" });
  });
});
